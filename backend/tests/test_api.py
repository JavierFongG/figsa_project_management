from datetime import date, timedelta

import pytest

from app.services.snapshot import today_gt

TODAY = today_gt()  # Guatemala time, like the API
iso = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731


async def test_health_and_auth(client, editor, viewer):
    assert (await client.get("/projects")).status_code == 401
    bad = await client.post("/auth/login", json={"email": "editor@test.com", "password": "nope"})
    assert bad.status_code == 401
    me = await client.get("/auth/me", headers=viewer)
    assert me.json()["role"] == "viewer" and me.json()["can_write"] is False


async def test_viewer_cannot_write(client, viewer):
    r = await client.post("/projects", headers=viewer, json={"id": "ZZ", "name": "Z"})
    assert r.status_code == 403


async def test_project_and_activity_flow(client, editor):
    r = await client.post("/projects", headers=editor, json={"id": "cem", "name": "Cemaco", "short_name": "CEM", "priority": "Alta", "exchange_rate": 7.8})
    assert r.status_code == 201 and r.json()["id"] == "CEM"
    assert (await client.post("/projects", headers=editor, json={"id": "CEM", "name": "dup"})).status_code == 409

    mk = lambda id, **kw: client.post("/activities", headers=editor, json={"id": id, "project_id": "CEM", "description": f"Act {id}", **kw})  # noqa: E731
    a = await mk("cem-01", start_date=iso(-6), duration_days=3, date_confidence="confirmada")
    assert a.status_code == 201, a.text
    body = a.json()
    assert body["id"] == "CEM-01" and body["end_date"] == iso(-4)                # end = start + duration - 1
    assert body["status_info"]["code"] == "atrasada" and body["baseline_start"] == iso(-6)

    assert (await mk("CEM-01")).status_code == 409                                # duplicate code
    assert (await mk("CEM-02", dependencies=["NOPE"])).status_code == 422          # unknown dependency
    b = await mk("CEM-02", duration_days=2, dependencies=["CEM-01"])
    assert b.status_code == 201 and b.json()["dependencies"] == ["CEM-01"]
    # cycle: CEM-01 cannot depend on CEM-02
    cyc = await client.patch("/activities/CEM-01", headers=editor, json={"dependencies": ["CEM-02"]})
    assert cyc.status_code == 422 and "ciclo" in cyc.json()["detail"]
    # end before start
    bad = await client.patch("/activities/CEM-01", headers=editor, json={"end_date": iso(-10)})
    assert bad.status_code == 422

    # optimistic concurrency
    cur = (await client.get("/activities/CEM-01", headers=editor)).json()
    ok = await client.patch("/activities/CEM-01", headers={**editor, "If-Match": cur["updated_at"]}, json={"owner": "Ana"})
    assert ok.status_code == 200
    stale = await client.patch("/activities/CEM-01", headers={**editor, "If-Match": cur["updated_at"]}, json={"owner": "Beto"})
    assert stale.status_code == 412

    # CEM-02 is not actionable until CEM-01 is done; completing it unlocks
    pr = (await client.get("/priorities", headers=editor)).json()
    assert [p["activity_id"] for p in pr] == ["CEM-01"]
    done = await client.post("/activities/CEM-01/complete", headers=editor)
    assert done.json()["status"] == "completada" and done.json()["actual_date"] == TODAY.isoformat()
    pr = (await client.get("/priorities", headers=editor)).json()
    assert [p["activity_id"] for p in pr] == ["CEM-02"]

    note = await client.post("/activities/CEM-02/notes", headers=editor, json={"body": "Llamé al proveedor"})
    assert note.status_code == 201
    hist = (await client.get("/audit", headers=editor, params={"entity": "activity", "entity_id": "CEM-01"})).json()
    assert any(h["field"] == "Estado" and h["after_value"] == "Completada" for h in hist)


async def test_views(client, editor):
    pf = (await client.get("/dashboard/portfolio", headers=editor)).json()
    cem = next(p for p in pf["projects"] if p["id"] == "CEM")
    assert cem["total_activities"] == 2 and cem["done_activities"] == 1
    tasks = (await client.get("/dashboard/my-tasks", headers=editor, params={"days": 7})).json()
    assert [t["id"] for t in tasks["ready"]] == ["CEM-02"]
    assert [t["id"] for t in tasks["done"]] == ["CEM-01"]
    sch = (await client.get("/schedule", headers=editor, params={"project_id": "CEM"})).json()
    assert {a["id"] for a in sch["activities"]} == {"CEM-01", "CEM-02"}
    rep = (await client.get("/reports/daily", headers=editor)).json()["text"]
    assert "ACTUALIZACIÓN DE PROYECTOS FIGSA" in rep and "CEM-01" in rep
    wa = (await client.post("/reports/whatsapp", headers=editor, json={"audience": "jefe", "period": "semana"})).json()
    assert wa["text"].startswith("Buen día.")


async def test_budget_purchases_per_diem_and_finance(client, editor):
    line = await client.post("/projects/CEM/budget-lines", headers=editor, json={"code": "1.1", "phase": "Equipos", "material": "Inversores", "quantity": 2, "unit_price": 5000})
    assert line.status_code == 201 and float(line.json()["total"]) == 10000
    lid = line.json()["id"]

    other = await client.post("/projects", headers=editor, json={"id": "MA", "name": "Otro"})
    assert other.status_code == 201
    wrong = await client.post("/purchases", headers=editor, json={"project_id": "MA", "product": "x", "budget_line_id": lid})
    assert wrong.status_code == 422 and "es del proyecto CEM" in wrong.json()["detail"]

    p1 = await client.post("/purchases", headers=editor, json={"project_id": "CEM", "product": "Inversor 10kW", "status": "realizada", "total_amount": 3000, "budget_line_id": lid})
    assert p1.status_code == 201 and p1.json()["completed_on"] == TODAY.isoformat()
    await client.post("/purchases", headers=editor, json={"project_id": "CEM", "product": "Cable", "status": "anticipo", "total_amount": 5000, "advance_paid": 1000, "budget_line_id": lid})
    await client.post("/purchases", headers=editor, json={"project_id": "CEM", "product": "Importado", "status": "recibida", "currency": "USD", "total_amount": 100, "budget_line_id": lid})
    await client.post("/purchases", headers=editor, json={"project_id": "CEM", "product": "Sin rubro", "status": "realizada", "total_amount": 50})
    pd = await client.post("/per-diems", headers=editor, json={"project_id": "CEM", "entry_date": iso(0), "person": "Ana", "amount": 200, "category": "alimentacion", "budget_line_id": lid, "detail": "Almuerzo"})
    assert pd.status_code == 201
    await client.post("/per-diems", headers=editor, json={"project_id": "CEM", "entry_date": iso(0), "person": "Ana", "kind": "anticipo", "amount": 500})

    fin = (await client.get("/projects/CEM/finance", headers=editor)).json()
    row = fin["lines"][0]
    assert row["executed"] == pytest.approx(3000 + 1000 + 100 * 7.8 + 200)       # project rate 7.8
    assert row["committed"] == pytest.approx(4000)
    assert fin["totals"]["unlabeled_count"] == 1 and fin["usd_purchases"] == 1

    done = await client.post(f"/budget-lines/{lid}/complete", headers=editor)
    assert done.json()["completed"] is True
    fin = (await client.get("/projects/CEM/finance", headers=editor)).json()
    assert fin["lines"][0]["savings"] == pytest.approx(10000 - fin["lines"][0]["executed"])

    s = (await client.get("/per-diems/summary", headers=editor)).json()
    ana = s["people"][0]
    assert ana["advances"] == 500 and ana["expenses"] == 200 and ana["balance"] == 300
    assert "POR PERSONA" in s["text"]

    # deleting the budget line clears the tag instead of deleting purchases
    assert (await client.delete(f"/budget-lines/{lid}", headers=editor)).status_code == 204
    purchases = (await client.get("/purchases", headers=editor, params={"project_id": "CEM"})).json()
    assert len(purchases) == 4 and all(p["budget_line_id"] is None for p in purchases)


async def test_externals_and_blocking(client, editor):
    x = await client.post("/externals", headers=editor, json={"project_id": "CEM", "counterparty": "Makbi", "subject": "Planos aprobados", "status": "esperando", "blocks": ["CEM-02"]})
    assert x.status_code == 201 and x.json()["requested_on"] == TODAY.isoformat()
    assert (await client.post("/externals", headers=editor, json={"project_id": "CEM", "counterparty": "A", "subject": "B", "blocks": ["NOPE"]})).status_code == 422
    act = (await client.get("/activities/CEM-02", headers=editor)).json()
    assert act["status_info"]["code"] == "bloqueada_tercero"
    res = await client.post(f"/externals/{x.json()['id']}/resolve", headers=editor)
    assert res.json()["status"] == "resuelto"
    act = (await client.get("/activities/CEM-02", headers=editor)).json()
    assert act["status_info"]["code"] != "bloqueada_tercero"


async def test_staff_overlap_is_rejected(client, editor):
    w = (await client.post("/workers", headers=editor, json={"name": "Carlos", "role": "tecnico"})).json()
    a1 = await client.post("/assignments", headers=editor, json={"worker_id": w["id"], "project_id": "CEM", "start_date": iso(1), "end_date": iso(5)})
    assert a1.status_code == 201
    clash = await client.post("/assignments", headers=editor, json={"worker_id": w["id"], "project_id": "MA", "start_date": iso(5), "end_date": iso(8)})
    assert clash.status_code == 409 and "Conflicto" in clash.json()["detail"]
    ok = await client.post("/assignments", headers=editor, json={"worker_id": w["id"], "project_id": "MA", "start_date": iso(6)})
    assert ok.status_code == 201
    assert (await client.delete(f"/workers/{w['id']}", headers=editor)).status_code == 409   # has assignments


async def test_billing(client, editor):
    b = await client.post("/billing", headers=editor, json={"project_id": "CEM", "concept": "Anticipo 50%", "amount": 12000})
    assert b.status_code == 201
    up = await client.patch(f"/billing/{b.json()['id']}", headers=editor, json={"status": "facturado"})
    assert up.json()["status"] == "facturado"


async def test_file_upload_without_drive_config_is_a_clear_error(client, editor):
    p = (await client.post("/purchases", headers=editor, json={"project_id": "CEM", "product": "Con archivo"})).json()
    r = await client.post(f"/purchases/{p['id']}/files", headers=editor, params={"kind": "factura"}, files={"file": ("f.pdf", b"%PDF-1.4 test", "application/pdf")})
    assert r.status_code == 422 and "carpeta de Drive" in r.json()["detail"]
