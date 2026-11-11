from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from app.core import db
from app.core.config import settings
from app.core.deps import current_user
from app.schemas import WhatsAppIn
from app.services import views
from app.services.labels import fd, fdy
from app.services.snapshot import load_model, note_stats

router = APIRouter(prefix="/reports", tags=["reports"])

PERIODS = ("hoy", "semana", "mes")


def _local_date(ts: datetime) -> date:
    return ts.astimezone(ZoneInfo(settings.tz)).date()


@router.get("/daily")
async def daily(days: int = 7, project_id: str | None = None, front: str | None = None, as_of: date | None = None, _: dict = Depends(current_user)):
    """Plain-text progress update (the 'Resumen para compartir' of Mis tareas)."""
    days = max(1, min(days, 60))
    async with db.tx() as c:
        m = await load_model(c, as_of)
        notes = await note_stats(c)
        all_notes = await db.fetch(c, "activity_note", order=db.T("activity_note").c.created_at)
    recent = [
        {**n, "project_id": m.A[n["activity_id"]]["project_id"]} for n in all_notes
        if n["activity_id"] in m.A and _local_date(n["created_at"]) >= m.today - timedelta(days=days)
        and (not project_id or m.A[n["activity_id"]]["project_id"] == project_id.upper())
    ]
    text = views.build_daily_report(m, notes, recent, days, project_id.upper() if project_id else None, front)
    return {"text": text}


async def _period_data(c, m, a: date, b: date, project_id: str | None):
    pid = project_id.upper() if project_id else None
    in_p = (lambda x: x == pid) if pid else (lambda x: True)
    acts = [x for x in m.A.values() if x["status"] == "completada" and x.get("actual_date") and a <= x["actual_date"] <= b and in_p(x["project_id"])]
    notes = [
        {**n, "project_id": m.A[n["activity_id"]]["project_id"]}
        for n in await db.fetch(c, "activity_note", order=db.T("activity_note").c.created_at.desc())
        if n["activity_id"] in m.A and a <= _local_date(n["created_at"]) <= b and in_p(m.A[n["activity_id"]]["project_id"])
    ]
    per_diems = await db.fetch(c, "per_diem")
    payments = [p for p in views.payments_in_range(m, per_diems, a, b) if in_p(p["project_id"])]
    purchases = {str(p["id"]): p for p in m.purchases}
    files = []
    for f in await db.fetch(c, "purchase_file"):
        p = purchases.get(str(f["purchase_id"]))
        if p and a <= _local_date(f["uploaded_at"]) <= b and in_p(p["project_id"]):
            files.append({**f, "project_id": p["project_id"], "product": p["product"]})
    ext = [x for x in m.externals.values() if x["status"] == "resuelto" and x.get("resolved_on") and a <= x["resolved_on"] <= b and in_p(x["project_id"])]
    lines = [x for x in await db.fetch(c, "budget_line") if x["completed"] and x.get("completed_on") and a <= x["completed_on"] <= b and in_p(x["project_id"])]
    hist = [h for h in await db.fetch(c, "audit_log", order=db.T("audit_log").c.ts.desc(), limit=500)
            if a <= _local_date(h["ts"]) <= b and (not pid or h["project_id"] == pid)][:150]
    per: dict[str, dict] = {}

    def bump(p, k, v=1):
        if p:
            r = per.setdefault(p, {"activities": 0, "notes": 0, "payments": 0, "amount": 0.0, "files": 0, "externals": 0})
            r[k] += v

    for x in acts:
        bump(x["project_id"], "activities")
    for x in notes:
        bump(x["project_id"], "notes")
    for g in payments:
        bump(g["project_id"], "payments")
        bump(g["project_id"], "amount", g["amount"])
    for f in files:
        bump(f["project_id"], "files")
    for x in ext:
        bump(x["project_id"], "externals")
    return {"activities": acts, "notes": notes, "payments": payments, "files": files, "externals": ext, "lines": lines, "history": hist, "per_project": per}


@router.get("/summary")
async def summary(period: str = "semana", project_id: str | None = None, as_of: date | None = None, _: dict = Depends(current_user)):
    period = period if period in PERIODS else "semana"
    async with db.tx() as c:
        m = await load_model(c, as_of)
        a, b, label = views.range_for(m.today, period)
        data = await _period_data(c, m, a, b, project_id)
    text = views.summary_text(label, a, b, data, m)
    return {"period": period, "label": label, "start": a, "end": b, **data, "text": text}


@router.post("/whatsapp")
async def whatsapp(body: WhatsAppIn, as_of: date | None = None, _: dict = Depends(current_user)):
    """Status message from the fixed template (no AI)."""
    async with db.tx() as c:
        m = await load_model(c, as_of)
        a, b, label = views.range_for(m.today, body.period)
        data = await _period_data(c, m, a, b, body.project_id)
    d = views.whatsapp_data(m, data, a, b, body.project_id.upper() if body.project_id else None, body.audience)
    rng = fdy(a) if a == b else f"{fd(a)} – {fdy(b)}"
    return {"text": views.whatsapp_template(d, label, rng, body.audience), "has_content": bool(d["projects"])}
