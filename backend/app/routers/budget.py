from fastapi import APIRouter, Depends, HTTPException

from app.core import db
from app.core.deps import current_user, require_editor
from app.schemas import BudgetLineIn, BudgetLinePatch
from app.services import audit, finance
from app.services.snapshot import today_gt

router = APIRouter(tags=["budget"])


def _q(v) -> str:
    return f"Q {float(v or 0):,.2f}"


def next_order(lines: list[dict], code: str, phase: str) -> float:
    """Place a new line after the same code, else after the last line of its phase, else at the end."""
    same = [x for x in lines if x["code"] == code]
    in_phase = [x for x in lines if x["phase"] == phase]
    after = same or in_phase
    if after:
        last = max(x["sort_order"] for x in after)
        nxt = [x["sort_order"] for x in lines if x["sort_order"] > last]
        return (last + min(nxt)) / 2 if nxt else last + 1
    return (max((x["sort_order"] for x in lines), default=0)) + 1


async def _project_or_404(c, pid: str) -> dict:
    p = await db.get(c, "project", pid.upper())
    if not p:
        raise HTTPException(404, "Proyecto no encontrado.")
    return p


@router.get("/projects/{pid}/budget-lines")
async def list_lines(pid: str, _: dict = Depends(current_user)):
    t = db.T("budget_line")
    async with db.tx() as c:
        await _project_or_404(c, pid)
        return await db.fetch(c, "budget_line", t.c.project_id == pid.upper(), order=t.c.sort_order)


@router.post("/projects/{pid}/budget-lines", status_code=201)
async def create_line(pid: str, body: BudgetLineIn, user: dict = Depends(require_editor)):
    pid = pid.upper()
    vals = body.model_dump()
    t = db.T("budget_line")
    async with db.tx() as c:
        await _project_or_404(c, pid)
        lines = await db.fetch(c, "budget_line", t.c.project_id == pid)
        vals["phase"] = (vals.get("phase") or "").strip() or "Otros"
        if not vals.get("activity"):
            vals["activity"] = vals.get("material")
        if not vals.get("activity"):
            raise HTTPException(422, "Escribe la actividad o el material.")
        vals = finance.prep_line(vals)
        if vals["completed"]:
            vals["completed_on"] = today_gt()
        vals.update(project_id=pid, sort_order=next_order(lines, vals["code"], vals["phase"]), source="Agregada en el tablero")
        row = await db.create(c, "budget_line", vals)
        await audit.write(c, user, "budget_line", row["id"], pid,
                          [(f"Línea de presupuesto agregada · {row['code']} {row.get('material') or row['activity']}", None, _q(row["total"]))])
        return row


@router.patch("/budget-lines/{lid}")
async def update_line(lid: str, body: BudgetLinePatch, user: dict = Depends(require_editor)):
    vals = body.model_dump(exclude_unset=True)
    async with db.tx() as c:
        old = await db.get(c, "budget_line", lid)
        if not old:
            raise HTTPException(404, "Línea no encontrada.")
        if "phase" in vals:
            vals["phase"] = (vals["phase"] or "").strip() or old["phase"] or "Otros"
        vals = finance.prep_line(vals, old)
        if "completed" in vals and bool(vals["completed"]) != bool(old["completed"]):
            vals["completed_on"] = today_gt() if vals["completed"] else None
        new = await db.patch(c, "budget_line", lid, vals)
        if str(old["total"]) != str(new["total"]):
            await audit.write(c, user, "budget_line", lid, new["project_id"],
                              [(f"Presupuesto {new['code']} {new.get('material') or new['activity']}", _q(old["total"]), _q(new["total"]))])
        return new


@router.post("/budget-lines/{lid}/complete")
async def complete_line(lid: str, user: dict = Depends(require_editor)):
    return await _set_completed(lid, True, user)


@router.post("/budget-lines/{lid}/reopen")
async def reopen_line(lid: str, user: dict = Depends(require_editor)):
    return await _set_completed(lid, False, user)


async def _set_completed(lid: str, flag: bool, user: dict):
    async with db.tx() as c:
        old = await db.get(c, "budget_line", lid)
        if not old:
            raise HTTPException(404, "Línea no encontrada.")
        new = await db.patch(c, "budget_line", lid, {"completed": flag, "completed_on": today_gt() if flag else None})
        await audit.write(c, user, "budget_line", lid, new["project_id"],
                          [(f"Línea {new['code']} {new.get('material') or new['activity']}", "Completada" if old["completed"] else "Abierta", "Completada" if flag else "Abierta")])
        return new


@router.delete("/budget-lines/{lid}", status_code=204)
async def delete_line(lid: str, user: dict = Depends(require_editor)):
    async with db.tx() as c:
        old = await db.get(c, "budget_line", lid)
        if not old:
            raise HTTPException(404, "Línea no encontrada.")
        await db.remove(c, "budget_line", lid)  # purchases/per-diems keep their rows with the tag cleared (FK SET NULL)
        await audit.write(c, user, "budget_line", lid, old["project_id"],
                          [(f"Línea de presupuesto borrada · {old['code']} {old.get('material') or old['activity']}", _q(old["total"]), None)])


@router.get("/projects/{pid}/finance")
async def project_finance(pid: str, _: dict = Depends(current_user)):
    pid = pid.upper()
    async with db.tx() as c:
        project = await _project_or_404(c, pid)
        lines = await db.fetch(c, "budget_line", db.T("budget_line").c.project_id == pid)
        purchases = await db.fetch(c, "purchase", db.T("purchase").c.project_id == pid)
        per_diems = await db.fetch(c, "per_diem", db.T("per_diem").c.project_id == pid)
    return finance.project_finance(project, lines, purchases, per_diems)


@router.get("/finance/projects")
async def projects_with_budget(_: dict = Depends(current_user)):
    """Projects that have at least one budget line (to fill the project switcher)."""
    async with db.tx() as c:
        lines = await db.fetch(c, "budget_line")
        projects = await db.fetch(c, "project", order=db.T("project").c.sort_order)
    ids = {ln["project_id"] for ln in lines}
    return [p for p in projects if p["id"] in ids]
