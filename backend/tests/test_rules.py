from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services import finance
from app.services.rules import Model, compute_schedule, would_cycle

TODAY = date(2026, 11, 11)
D = lambda n: TODAY + timedelta(days=n)  # noqa: E731


def act(id, project="P1", **kw):
    base = dict(id=id, project_id=project, description=f"Act {id}", type="ejecucion", front=None, owner=None, status="pendiente",
                start_date=None, end_date=None, duration_days=None, date_confidence="pendiente", actual_date=None,
                generates_income=False, needs_external=False)
    return {**base, **kw}


def model(acts, deps=(), projects=None, externals=(), blocks=(), purchases=(), assignments=(), workers=()):
    projects = projects or [dict(id="P1", name="Proyecto 1", short_name="P1", priority="Media", sort_order=0, scenario_start=None,
                                 req_technicians=None, req_helpers=None, staffing_activity_id=None)]
    return Model(projects=projects, activities=acts,
                 dependencies=[dict(activity_id=a, depends_on_id=b) for a, b in deps],
                 externals=list(externals), ext_blocks=list(blocks), purchases=list(purchases),
                 assignments=list(assignments), workers=list(workers), today=TODAY)


# ---------------------------------------------------------------- schedule
def test_dated_activity_uses_its_dates_and_confidence():
    a = act("A1", start_date=D(2), end_date=D(5), date_confidence="confirmada")
    b = act("A2", start_date=D(2), duration_days=3)
    s = compute_schedule({"A1": a, "A2": b}, {}, {}, TODAY)
    assert (s["A1"].start, s["A1"].end, s["A1"].kind) == (D(2), D(5), "conf")
    assert (s["A2"].end, s["A2"].kind) == (D(4), "est")  # start + duration - 1


def test_forward_pass_from_scenario_and_predecessors_never_before_today():
    a = act("A1", duration_days=3)
    b = act("A2", duration_days=2)
    c = act("A3")  # no duration -> zero length
    preds = {"A2": ["A1"], "A3": ["A2"]}
    s = compute_schedule({"A1": a, "A2": b, "A3": c}, preds, {"P1": D(-30)}, TODAY)  # scenario in the past
    assert s["A1"].start == TODAY and s["A1"].kind == "esc"
    assert s["A2"].start == D(3) and s["A2"].end == D(4)
    assert s["A3"].zero and s["A3"].start == D(5)


def test_undated_without_scenario_or_predecessors_is_unscheduled():
    s = compute_schedule({"A1": act("A1", duration_days=3)}, {}, {}, TODAY)
    assert s["A1"] is None


def test_completed_predecessor_without_date_is_skipped_but_with_date_counts():
    done_no_date = act("A1", status="completada")
    done_dated = act("A1", status="completada", actual_date=D(-2), start_date=D(-4))
    nxt = act("A2", duration_days=2)
    s1 = compute_schedule({"A1": done_no_date, "A2": nxt}, {"A2": ["A1"]}, {"P1": D(3)}, TODAY)
    assert s1["A2"].start == D(3)
    s2 = compute_schedule({"A1": done_dated, "A2": nxt}, {"A2": ["A1"]}, {}, TODAY)
    assert s2["A1"].kind == "real" and s2["A2"].start == TODAY  # D(-1) clamped to today


def test_cycle_does_not_hang():
    s = compute_schedule({"A1": act("A1", duration_days=1), "A2": act("A2", duration_days=1)}, {"A1": ["A2"], "A2": ["A1"]}, {"P1": D(1)}, TODAY)
    assert s["A1"] is None and s["A2"] is None


def test_would_cycle():
    succ = {"A": ["B"], "B": ["C"]}
    assert would_cycle("A", ["C"], succ) is True   # C is downstream of A
    assert would_cycle("C", ["A"], succ) is False  # A before C is fine


# ---------------------------------------------------------------- status
@pytest.mark.parametrize("kw,code", [
    (dict(status="completada"), "completada"),
    (dict(status="bloqueada"), "bloqueada"),
    (dict(start_date=D(-5), end_date=D(-1)), "atrasada"),
    (dict(start_date=D(-1), end_date=D(3)), "inicio_atrasado"),
    (dict(start_date=D(-1), end_date=D(3), status="proceso"), "proceso"),
    (dict(start_date=D(3), end_date=D(6)), "proxima"),       # starts in exactly 3 days
    (dict(start_date=D(4), end_date=D(6)), "pendiente"),     # 4 days is not "soon"
])
def test_status_boundaries(kw, code):
    a = act("A1", **kw)
    assert model([a]).status(a)["code"] == code


def test_open_external_blocks_activity_and_resolved_does_not():
    a = act("A1")
    ext_open = dict(id="x1", project_id="P1", status="esperando", counterparty="Makbi", subject="Planos", requested_on=D(-10))
    m = model([a], externals=[ext_open], blocks=[dict(external_id="x1", activity_id="A1")])
    assert m.status(a)["code"] == "bloqueada_tercero"
    m2 = model([a], externals=[{**ext_open, "status": "resuelto"}], blocks=[dict(external_id="x1", activity_id="A1")])
    assert m2.status(a)["code"] == "pendiente"


def test_dependency_violation():
    a = act("A1", start_date=D(0), end_date=D(5))
    b = act("A2", start_date=D(5), end_date=D(8))  # starts on the day A1 ends
    m = model([a, b], deps=[("A2", "A1")])
    assert m.violation(b) == "A1"
    b2 = act("A2", start_date=D(6), end_date=D(8))
    assert model([a, b2], deps=[("A2", "A1")]).violation(b2) is None


# ---------------------------------------------------------------- critical path / priorities
def test_critical_path_marks_zero_slack_chain():
    a = act("A1", start_date=D(0), end_date=D(2), date_confidence="confirmada")
    b = act("A2", start_date=D(3), end_date=D(9), date_confidence="confirmada")
    side = act("A3", start_date=D(3), end_date=D(4), date_confidence="confirmada")
    m = model([a, b, side], deps=[("A2", "A1"), ("A3", "A1")])
    assert {"A1", "A2"} <= m.crit
    assert "A3" not in m.crit


def test_priority_ranking_and_tags():
    late = act("A1", start_date=D(-5), end_date=D(-1), date_confidence="confirmada")
    unlocks = act("A2", duration_days=2)
    dep = act("A3", duration_days=1)
    m = model([late, unlocks, dep], deps=[("A3", "A2")])
    pr = m.priorities(10)
    assert pr[0]["activity_id"] == "A1"  # late: +40
    tags = {t["text"] for p in pr for t in p["tags"]}
    assert "Desbloquea 1" in tags
    assert all(p["activity_id"] != "A3" for p in pr)  # A3 waits on A2, not actionable


def test_priorities_exclude_supply_milestones_and_blocked():
    sup = act("S1", type="suministro", duration_days=40)
    hito = act("H1", type="hito")
    m = model([sup, hito])
    assert m.priorities(10) == []


def test_long_lead_supply_boosts_predecessor():
    pre = act("A1", duration_days=2)
    sup = act("S1", type="suministro", duration_days=45)
    m = model([pre, sup], deps=[("S1", "A1")])
    tags = [t["text"] for t in m.priorities(5)[0]["tags"]]
    assert "Entrega larga" in tags


# ---------------------------------------------------------------- risks
def test_risks_cover_late_purchase_external():
    late = act("A1", start_date=D(-5), end_date=D(-1))
    purchase = dict(id="c1", project_id="P1", status="cotizacion", product="Inversor", supplier="X", lead_time_days=75, lead_time_source=None,
                    needed_by=D(5), currency="GTQ")
    ext = dict(id="x1", project_id="P1", status="esperando", counterparty="Celasa", subject="Permiso", requested_on=D(-9))
    m = model([late], purchases=[purchase], externals=[ext])
    titles = " | ".join(r["title"] for r in m.risks())
    assert "A1" in titles and "Inversor" in titles and "Celasa" in titles
    sev = {r["severity"] for r in m.risks()}
    assert "bad" in sev and "warn" in sev


# ---------------------------------------------------------------- staffing
def test_staff_needs_counts_roles_in_window():
    projects = [dict(id="P1", name="P1", short_name="P1", priority="Media", sort_order=0, scenario_start=None,
                     req_technicians=2, req_helpers=1, staffing_activity_id="A1")]
    a = act("A1", start_date=D(1), end_date=D(5), date_confidence="confirmada")
    workers = [dict(id="w1", role="tecnico", active=True), dict(id="w2", role="ayudante", active=True)]
    asg = [dict(id="g1", worker_id="w1", project_id="P1", start_date=D(2), end_date=D(3)),
           dict(id="g2", worker_id="w2", project_id="P1", start_date=D(20), end_date=D(22))]  # outside the window
    n = model([a], projects=projects, workers=workers, assignments=asg).staff_needs()[0]
    assert n["assigned_technicians"] == 1 and n["assigned_helpers"] == 0 and n["missing"] == 2


# ---------------------------------------------------------------- finance
def test_finance_execution_rules_and_usd():
    project = dict(id="P1", exchange_rate=None)
    line = dict(id="L1", project_id="P1", code="1.1", phase="Fase 1", activity="Inversores", material=None, total=Decimal("10000"),
                completed=False, sort_order=1, review_note=None)
    base = dict(project_id="P1", budget_line_id="L1", currency="GTQ", total_amount=None, advance_paid=None, product="x", supplier=None,
                ordered_on=None, invoice_mode=None)
    purchases = [
        {**base, "id": "a", "status": "realizada", "total_amount": Decimal("3000")},                                # done -> 3000
        {**base, "id": "b", "status": "anticipo", "total_amount": Decimal("5000"), "advance_paid": Decimal("1000")},  # advance only
        {**base, "id": "c", "status": "recibida", "currency": "USD", "total_amount": Decimal("100")},               # 100 * 7.70
        {**base, "id": "d", "status": "realizada", "budget_line_id": None, "total_amount": Decimal("50")},          # unlabeled
    ]
    per_diems = [
        dict(id="p1", project_id="P1", kind="gasto", amount=Decimal("200"), budget_line_id="L1", person="Ana", detail="Almuerzo", category="alimentacion", entry_date=TODAY),
        dict(id="p2", project_id="P1", kind="anticipo", amount=Decimal("500"), budget_line_id=None, person="Ana", detail=None, category=None, entry_date=TODAY),
    ]
    r = finance.project_finance(project, [line], purchases, per_diems)
    row = r["lines"][0]
    assert row["executed"] == pytest.approx(3000 + 1000 + 770 + 200)
    assert row["committed"] == pytest.approx(4000)  # 5000 total - 1000 advance
    assert r["totals"]["unlabeled_count"] == 1 and r["totals"]["unlabeled_amount"] == pytest.approx(50)
    assert r["usd_purchases"] == 1
    assert row["savings"] is None  # not completed
    r2 = finance.project_finance({**project, "exchange_rate": Decimal("8")}, [{**line, "completed": True}], purchases, per_diems)
    assert r2["lines"][0]["executed"] == pytest.approx(3000 + 1000 + 800 + 200)
    assert r2["lines"][0]["savings"] == pytest.approx(10000 - 5000)


def test_prep_line_total_and_review_note():
    v = finance.prep_line({"quantity": Decimal("4"), "unit_price": Decimal("250")})
    assert v["total"] == Decimal("1000.0") and v["review_note"] is None
    v = finance.prep_line({"quantity": Decimal("4"), "unit_price": Decimal("250"), "total": Decimal("1500")})
    assert "P.U." in v["review_note"]
    v = finance.prep_line({})
    assert v["review_note"] == "Sin monto en el presupuesto"
