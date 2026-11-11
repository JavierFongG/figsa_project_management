from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete as sa_delete, insert as sa_insert

from app.core import db
from app.core.deps import check_etag, current_user, require_editor
from app.schemas import ActivityIn, ActivityPatch, CompleteIn, NoteIn
from app.services import audit
from app.services.rules import DAY, nat_key, would_cycle
from app.services.snapshot import load_model, note_stats, today_gt

router = APIRouter(prefix="/activities", tags=["activities"])

TRACK = {
    "status": "Estado", "start_date": "Inicio", "end_date": "Fin", "actual_date": "Fecha real",
    "duration_days": "Duración", "owner": "Responsable", "date_confidence": "Calidad de fecha",
}


def normalize(vals: dict, existing: dict | None, today: date) -> dict:
    """Date rules from the artifact: end = start + duration - 1, duration = end - start + 1,
    completed gets an actual date, first saved dates become the baseline."""
    cur = {**(existing or {}), **vals}
    s, e, d = cur.get("start_date"), cur.get("end_date"), cur.get("duration_days")
    if s and "start_date" in vals and "end_date" not in vals and existing and d and d > 0:
        vals["end_date"] = s + (d - 1) * DAY  # moving the start shifts the end
        e = vals["end_date"]
    if s and e and e < s:
        raise HTTPException(422, "El fin no puede ser anterior al inicio.")
    if s and not e and d and d > 0:
        vals["end_date"] = s + (d - 1) * DAY
        e = vals["end_date"]
    if s and e and d is None:
        vals["duration_days"] = (e - s).days + 1
    if cur.get("status") == "completada" and not cur.get("actual_date"):
        vals["actual_date"] = today
    if s and not cur.get("baseline_start"):
        vals["baseline_start"] = s
    if e and not cur.get("baseline_end"):
        vals["baseline_end"] = e
    return vals


async def _check_deps(c, act_id: str, deps: list[str]) -> list[str]:
    deps = sorted({d.strip().upper() for d in deps if d and d.strip()})
    if act_id in deps:
        raise HTTPException(422, "Una actividad no puede depender de sí misma.")
    existing = {r["id"] for r in await db.fetch(c, "activity", db.T("activity").c.id.in_(deps))} if deps else set()
    bad = [d for d in deps if d not in existing]
    if bad:
        raise HTTPException(422, "Dependencias no válidas: " + ", ".join(bad))
    succ: dict[str, list[str]] = {}
    for r in await db.fetch(c, "activity_dependency"):
        succ.setdefault(r["depends_on_id"], []).append(r["activity_id"])
    if would_cycle(act_id, deps, succ):
        raise HTTPException(422, "Esas dependencias crean un ciclo entre actividades.")
    return deps


async def _set_deps(c, act_id: str, deps: list[str]) -> None:
    t = db.T("activity_dependency")
    await c.execute(sa_delete(t).where(t.c.activity_id == act_id))
    if deps:
        await c.execute(sa_insert(t), [{"activity_id": act_id, "depends_on_id": d} for d in deps])


async def _one(c, act_id: str, with_notes: bool = False) -> dict:
    m = await load_model(c)
    a = m.A.get(act_id)
    if not a:
        raise HTTPException(404, "Actividad no encontrada.")
    out = m.describe(a)
    if with_notes:
        t = db.T("activity_note")
        out["notes"] = await db.fetch(c, "activity_note", t.c.activity_id == act_id, order=t.c.created_at.desc())
        out["note_count"] = len(out["notes"])
        out["last_note"] = out["notes"][0] if out["notes"] else None
    return out


@router.get("")
async def list_activities(project_id: str | None = None, as_of: date | None = None, _: dict = Depends(current_user)):
    async with db.tx() as c:
        m = await load_model(c, as_of)
        notes = await note_stats(c)
    rows = []
    for a in m.A.values():
        if project_id and a["project_id"] != project_id.upper():
            continue
        d = m.describe(a)
        st = notes.get(a["id"]) or {"count": 0, "last": None}
        d["last_note"], d["note_count"] = st["last"], st["count"]
        rows.append(d)
    order = {p["id"]: (p["sort_order"], nat_key(p["id"])) for p in m.P.values()}
    rows.sort(key=lambda r: (order.get(r["project_id"], (99, [])), nat_key(r["id"])))
    return rows


@router.get("/{act_id}")
async def get_activity(act_id: str, _: dict = Depends(current_user)):
    async with db.tx() as c:
        return await _one(c, act_id.upper(), with_notes=True)


@router.post("", status_code=201)
async def create_activity(body: ActivityIn, user: dict = Depends(require_editor)):
    vals = body.model_dump()
    deps = vals.pop("dependencies")
    aid = vals["id"]
    async with db.tx() as c:
        if await db.get(c, "activity", aid):
            raise HTTPException(409, f"Ya existe una actividad con el código {aid}.")
        if not await db.get(c, "project", vals["project_id"]):
            raise HTTPException(422, f"No existe el proyecto {vals['project_id']}.")
        deps = await _check_deps(c, aid, deps)
        vals = normalize(vals, None, today_gt())
        row = await db.create(c, "activity", vals)
        await _set_deps(c, aid, deps)
        await audit.write(c, user, "activity", aid, row["project_id"], [("Creada", None, row["description"])])
        return await _one(c, aid, with_notes=True)


@router.patch("/{act_id}")
async def update_activity(act_id: str, body: ActivityPatch, request: Request, user: dict = Depends(require_editor)):
    act_id = act_id.upper()
    vals = body.model_dump(exclude_unset=True)
    vals.pop("id", None)
    deps = vals.pop("dependencies", None)
    async with db.tx() as c:
        old = await db.get(c, "activity", act_id)
        if not old:
            raise HTTPException(404, "Actividad no encontrada.")
        check_etag(request, old)
        if vals.get("project_id") and not await db.get(c, "project", vals["project_id"]):
            raise HTTPException(422, f"No existe el proyecto {vals['project_id']}.")
        vals = normalize(vals, old, today_gt())
        new = await db.patch(c, "activity", act_id, vals)
        changes = audit.diff(old, new, TRACK)
        if deps is not None:
            deps = await _check_deps(c, act_id, deps)
            before = sorted(r["depends_on_id"] for r in await db.fetch(c, "activity_dependency", db.T("activity_dependency").c.activity_id == act_id))
            if before != deps:
                await _set_deps(c, act_id, deps)
                changes.append(("Dependencias", ", ".join(before) or None, ", ".join(deps) or None))
        await audit.write(c, user, "activity", act_id, new["project_id"], changes)
        return await _one(c, act_id, with_notes=True)


@router.post("/{act_id}/complete")
async def complete_activity(act_id: str, body: CompleteIn | None = None, user: dict = Depends(require_editor)):
    act_id = act_id.upper()
    async with db.tx() as c:
        old = await db.get(c, "activity", act_id)
        if not old:
            raise HTTPException(404, "Actividad no encontrada.")
        day = (body.actual_date if body else None) or today_gt()
        new = await db.patch(c, "activity", act_id, {"status": "completada", "actual_date": day})
        await audit.write(c, user, "activity", act_id, new["project_id"], audit.diff(old, new, TRACK))
        return await _one(c, act_id)


@router.post("/{act_id}/reopen")
async def reopen_activity(act_id: str, user: dict = Depends(require_editor)):
    act_id = act_id.upper()
    async with db.tx() as c:
        old = await db.get(c, "activity", act_id)
        if not old:
            raise HTTPException(404, "Actividad no encontrada.")
        new = await db.patch(c, "activity", act_id, {"status": "pendiente", "actual_date": None})
        await audit.write(c, user, "activity", act_id, new["project_id"], audit.diff(old, new, TRACK))
        return await _one(c, act_id)


@router.delete("/{act_id}", status_code=204)
async def delete_activity(act_id: str, user: dict = Depends(require_editor)):
    act_id = act_id.upper()
    async with db.tx() as c:
        old = await db.get(c, "activity", act_id)
        if not old:
            raise HTTPException(404, "Actividad no encontrada.")
        await db.remove(c, "activity", act_id)
        await audit.write(c, user, "activity", act_id, old["project_id"], [("Eliminada", old["description"], None)])


@router.get("/{act_id}/notes")
async def list_notes(act_id: str, _: dict = Depends(current_user)):
    t = db.T("activity_note")
    async with db.tx() as c:
        return await db.fetch(c, "activity_note", t.c.activity_id == act_id.upper(), order=t.c.created_at.desc())


@router.post("/{act_id}/notes", status_code=201)
async def add_note(act_id: str, body: NoteIn, user: dict = Depends(require_editor)):
    act_id = act_id.upper()
    async with db.tx() as c:
        a = await db.get(c, "activity", act_id)
        if not a:
            raise HTTPException(404, "Actividad no encontrada.")
        note = await db.create(c, "activity_note", {"activity_id": act_id, "body": body.body, "author_id": user["id"]})
        await audit.write(c, user, "activity", act_id, a["project_id"], [("Comentario", None, body.body)])
    return note
