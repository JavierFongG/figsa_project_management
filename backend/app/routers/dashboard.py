from datetime import date

from fastapi import APIRouter, Depends

from app.core import db
from app.core.deps import current_user
from app.services import views
from app.services.rules import nat_key
from app.services.snapshot import load_model, note_stats

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/portfolio")
async def portfolio(as_of: date | None = None, _: dict = Depends(current_user)):
    async with db.tx() as c:
        m = await load_model(c, as_of)
    return views.portfolio(m)


@router.get("/dashboard/my-tasks")
async def my_tasks(days: int = 7, project_id: str | None = None, front: str | None = None, as_of: date | None = None, _: dict = Depends(current_user)):
    async with db.tx() as c:
        m = await load_model(c, as_of)
        notes = await note_stats(c)
    return views.task_groups(m, notes, max(1, min(days, 60)), project_id.upper() if project_id else None, front)


@router.get("/priorities")
async def priorities(limit: int = 10, project_id: str | None = None, as_of: date | None = None, _: dict = Depends(current_user)):
    async with db.tx() as c:
        m = await load_model(c, as_of)
    out = []
    for p in m.priorities(limit, project_id.upper() if project_id else None):
        out.append({**p, "activity": m.describe(m.A[p["activity_id"]])})
    return out


@router.get("/risks")
async def risks(project_id: str | None = None, as_of: date | None = None, _: dict = Depends(current_user)):
    async with db.tx() as c:
        m = await load_model(c, as_of)
    order = {"bad": 0, "warn": 1}
    return sorted(m.risks(project_id.upper() if project_id else None), key=lambda r: order.get(r["severity"], 2))


@router.get("/schedule")
async def schedule(project_id: str | None = None, as_of: date | None = None, _: dict = Depends(current_user)):
    """Gantt data: every activity with its computed dates, status, critical flag and dependency list."""
    async with db.tx() as c:
        m = await load_model(c, as_of)
    pid = project_id.upper() if project_id else None
    rows = []
    for a in m.A.values():
        if pid and a["project_id"] != pid:
            continue
        d = m.describe(a)
        rows.append({k: d[k] for k in (
            "id", "project_id", "description", "type", "front", "status", "owner", "duration_days", "date_confidence",
            "dependencies", "unlocks", "status_info", "sched", "critical", "violation", "blocked_by",
        )})
    order = {p["id"]: (p["sort_order"], nat_key(p["id"])) for p in m.P.values()}
    rows.sort(key=lambda r: (order.get(r["project_id"], (99, [])), nat_key(r["id"])))
    projects = [p for p in m.P.values() if not pid or p["id"] == pid]
    assumed = [r["id"] for r in rows if r["sched"] and r["sched"]["kind"] == "esc" and r["sched"]["zero"] and r["type"] != "hito"]
    unscheduled = [r["id"] for r in rows if r["status"] != "completada" and not r["sched"]]
    return {"today": m.today, "projects": sorted(projects, key=lambda p: (p["sort_order"], nat_key(p["id"]))), "activities": rows,
            "assumed_zero_duration": assumed, "unscheduled": unscheduled}
