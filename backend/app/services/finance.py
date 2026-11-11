"""Budget vs executed per project.

Rules (same as the artifact):
- A purchase is *done* when status is realizada or recibida. Done: executed = total (or advance if no total).
  Not done: executed = advance paid only. Committed = remaining total - executed.
- Per-diem *gastos* are executed in full. Anticipos are cash handed out and do not count as spending.
- USD amounts convert at the project's exchange rate (default 7.70).
- Savings are only reported on lines marked completed: budget - executed.
"""
from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal

from app.core.config import settings
from app.services.labels import PURCHASE_STATUS


def _n(v) -> float | None:
    return None if v is None else float(v)


def is_done(c: dict) -> bool:
    return c["status"] in ("realizada", "recibida")


def executed_native(c: dict) -> float | None:
    if is_done(c):
        t = _n(c.get("total_amount"))
        return t if t is not None else _n(c.get("advance_paid"))
    return _n(c.get("advance_paid"))


def to_q(v: float | None, currency: str, rate: float) -> float | None:
    if v is None:
        return None
    return v * rate if currency == "USD" else v


def rate_of(project: dict) -> float:
    r = project.get("exchange_rate")
    return float(r) if r else settings.default_exchange_rate


def line_total(line: dict) -> float:
    return _n(line.get("total")) or 0.0


def project_finance(project: dict, lines: list[dict], purchases: list[dict], per_diems: list[dict]) -> dict:
    rate = rate_of(project)
    by_id: OrderedDict[str, dict] = OrderedDict()
    for ln in sorted(lines, key=lambda x: (x.get("sort_order") or 0)):
        by_id[str(ln["id"])] = {**ln, "budget": line_total(ln), "executed": 0.0, "committed": 0.0, "movements": []}

    unlabeled: list[dict] = []
    usd_count = 0
    for c in purchases:
        if c["currency"] == "USD":
            usd_count += 1
        ex = to_q(executed_native(c), c["currency"], rate) or 0.0
        total_q = to_q(_n(c.get("total_amount")), c["currency"], rate)
        done = is_done(c)
        state = "ejecutado" if done else ("anticipo" if (_n(c.get("advance_paid")) or 0) > 0 else "pendiente")
        mov = {
            "kind": "compra", "id": str(c["id"]), "title": c["product"], "party": c.get("supplier"),
            "date": c.get("ordered_on"), "executed": ex, "total": total_q, "state": state,
            "status_label": PURCHASE_STATUS.get(c["status"], c["status"]), "currency": c["currency"],
            "invoice_mode": c.get("invoice_mode"),
        }
        key = str(c["budget_line_id"]) if c.get("budget_line_id") else None
        row = by_id.get(key) if key else None
        if row is None:
            if ex > 0:
                unlabeled.append(mov)
            continue
        row["movements"].append(mov)
        row["executed"] += ex
        if not done and total_q is not None:
            row["committed"] += max(0.0, total_q - ex)

    for d in per_diems:
        if d["kind"] != "gasto":
            continue
        amount = _n(d["amount"]) or 0.0
        mov = {
            "kind": "viatico", "id": str(d["id"]), "title": d.get("detail") or d.get("category") or "Viático",
            "party": d["person"], "date": d["entry_date"], "executed": amount, "total": amount, "state": "ejecutado",
            "status_label": "Viático", "currency": "GTQ", "invoice_mode": None,
        }
        key = str(d["budget_line_id"]) if d.get("budget_line_id") else None
        row = by_id.get(key) if key else None
        if row is None:
            unlabeled.append(mov)
            continue
        row["movements"].append(mov)
        row["executed"] += amount

    out_lines = []
    totals = {"budget": 0.0, "executed": 0.0, "committed": 0.0, "savings": 0.0, "completed_lines": 0, "lines": len(by_id), "review_lines": 0}
    phases: OrderedDict[str, dict] = OrderedDict()
    for row in by_id.values():
        b, e = row["budget"], row["executed"]
        row["available"] = b - e
        row["percent"] = (e / b * 100) if b > 0 else None
        row["savings"] = (b - e) if row["completed"] else None
        row["movement_count"] = len(row["movements"])
        out_lines.append(row)
        totals["budget"] += b
        totals["executed"] += e
        totals["committed"] += row["committed"]
        if row["completed"]:
            totals["savings"] += b - e
            totals["completed_lines"] += 1
        if row.get("review_note"):
            totals["review_lines"] += 1
        ph = phases.setdefault(row["phase"] or "Otros", {"phase": row["phase"] or "Otros", "budget": 0.0, "executed": 0.0, "savings": 0.0, "completed": 0, "lines": 0})
        ph["budget"] += b
        ph["executed"] += e
        ph["lines"] += 1
        if row["completed"]:
            ph["completed"] += 1
            ph["savings"] += b - e
    totals["available"] = totals["budget"] - totals["executed"]
    totals["percent"] = (totals["executed"] / totals["budget"] * 100) if totals["budget"] > 0 else None
    totals["unlabeled_count"] = len(unlabeled)
    totals["unlabeled_amount"] = sum(m["executed"] for m in unlabeled)
    return {
        "project_id": project["id"], "exchange_rate": rate, "usd_purchases": usd_count,
        "lines": out_lines, "phases": list(phases.values()), "unlabeled": unlabeled, "totals": totals,
    }


def prep_line(values: dict, existing: dict | None = None) -> dict:
    """Auto total (quantity x unit price) and a review note when numbers disagree."""
    merged = {**(existing or {}), **values}
    q = _n(merged.get("quantity"))
    p = _n(merged.get("unit_price"))
    total = _n(merged.get("total"))
    if total is None and q is not None and p is not None:
        total = round(q * p, 2)
        values["total"] = Decimal(str(total))
    if total is None:
        values["review_note"] = "Sin monto en el presupuesto"
    elif q is not None and p is not None and abs(q * p - total) > 1:
        values["review_note"] = f"P.U. × cantidad = Q {q * p:,.2f}; total registrado Q {total:,.2f}"
    else:
        values["review_note"] = None
    return values
