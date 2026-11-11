"""Billing (cobros), external items, workers, assignments and the audit trail."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete as sa_delete, insert as sa_insert

from app.core import db
from app.core.deps import check_etag, current_user, require_editor
from app.schemas import (AssignmentIn, AssignmentPatch, BillingIn, BillingPatch, ExternalIn, ExternalPatch,
                         ResolveIn, WorkerIn, WorkerPatch)
from app.services import audit
from app.services.labels import EXTERNAL_STATUS, BILLING_STATUS, fd, label
from app.services.snapshot import load_model, today_gt

router = APIRouter(tags=["misc"])


async def _need_project(c, pid: str):
    if not await db.get(c, "project", pid):
        raise HTTPException(422, f"No existe el proyecto {pid}.")


# ------------------------------------------------------------------ billing
@router.get("/billing", tags=["billing"])
async def list_billing(project_id: str | None = None, _: dict = Depends(current_user)):
    t = db.T("billing")
    where = [t.c.project_id == project_id.upper()] if project_id else []
    async with db.tx() as c:
        return await db.fetch(c, "billing", *where, order=(t.c.project_id, t.c.created_at))


@router.post("/billing", status_code=201, tags=["billing"])
async def create_billing(body: BillingIn, user: dict = Depends(require_editor)):
    vals = body.model_dump()
    async with db.tx() as c:
        await _need_project(c, vals["project_id"])
        row = await db.create(c, "billing", vals)
        await audit.write(c, user, "billing", row["id"], row["project_id"], [("Cobro creado", None, row["concept"])])
    return row


@router.patch("/billing/{bid}", tags=["billing"])
async def update_billing(bid: str, body: BillingPatch, user: dict = Depends(require_editor)):
    vals = body.model_dump(exclude_unset=True)
    async with db.tx() as c:
        old = await db.get(c, "billing", bid)
        if not old:
            raise HTTPException(404, "Cobro no encontrado.")
        new = await db.patch(c, "billing", bid, vals)
        if old["status"] != new["status"]:
            await audit.write(c, user, "billing", bid, new["project_id"],
                              [(f"Cobro · {new['concept']}", BILLING_STATUS[old["status"]], BILLING_STATUS[new["status"]])])
    return new


@router.delete("/billing/{bid}", status_code=204, tags=["billing"])
async def delete_billing(bid: str, user: dict = Depends(require_editor)):
    async with db.tx() as c:
        if not await db.remove(c, "billing", bid):
            raise HTTPException(404, "Cobro no encontrado.")


# ------------------------------------------------------------------ externals
async def _with_blocks(c, rows: list[dict]) -> list[dict]:
    blocks = await db.fetch(c, "external_item_blocks")
    by: dict = {}
    for b in blocks:
        by.setdefault(b["external_id"], []).append(b["activity_id"])
    today = today_gt()
    for r in rows:
        r["blocks"] = sorted(by.get(r["id"], []))
        r["waiting_days"] = (today - r["requested_on"]).days if r["status"] == "esperando" and r.get("requested_on") else None
    return rows


async def _set_blocks(c, ext_id, codes: list[str]):
    if codes:
        found = {r["id"] for r in await db.fetch(c, "activity", db.T("activity").c.id.in_(codes))}
        bad = [x for x in codes if x not in found]
        if bad:
            raise HTTPException(422, "Códigos no encontrados: " + ", ".join(bad))
    t = db.T("external_item_blocks")
    await c.execute(sa_delete(t).where(t.c.external_id == ext_id))
    if codes:
        await c.execute(sa_insert(t), [{"external_id": ext_id, "activity_id": x} for x in codes])


@router.get("/externals", tags=["externals"])
async def list_externals(project_id: str | None = None, status: str | None = None, _: dict = Depends(current_user)):
    t = db.T("external_item")
    where = []
    if project_id:
        where.append(t.c.project_id == project_id.upper())
    if status == "abiertos":
        where.append(t.c.status != "resuelto")
    elif status:
        where.append(t.c.status == status)
    async with db.tx() as c:
        rows = await _with_blocks(c, await db.fetch(c, "external_item", *where))
        m = await load_model(c)
    for r in rows:
        impact = set(r["blocks"])
        for b in r["blocks"]:
            impact.update(m.desc.get(b, []))
        r["impacted_activities"] = len(impact) if r["status"] != "resuelto" else 0
    rows.sort(key=lambda r: (r["status"] == "resuelto", 0 if r["blocks"] else 1, r["project_id"]))
    return rows


@router.post("/externals", status_code=201, tags=["externals"])
async def create_external(body: ExternalIn, user: dict = Depends(require_editor)):
    vals = body.model_dump()
    blocks = vals.pop("blocks")
    if vals["status"] == "esperando" and not vals.get("requested_on"):
        vals["requested_on"] = today_gt()
    async with db.tx() as c:
        await _need_project(c, vals["project_id"])
        row = await db.create(c, "external_item", vals)
        await _set_blocks(c, row["id"], blocks)
        await audit.write(c, user, "external", row["id"], row["project_id"], [(f"Externo · {row['counterparty']}", None, row["subject"])])
        return (await _with_blocks(c, [row]))[0]


@router.patch("/externals/{eid}", tags=["externals"])
async def update_external(eid: str, body: ExternalPatch, request: Request, user: dict = Depends(require_editor)):
    vals = body.model_dump(exclude_unset=True)
    blocks = vals.pop("blocks", None)
    async with db.tx() as c:
        old = await db.get(c, "external_item", eid)
        if not old:
            raise HTTPException(404, "Pendiente no encontrado.")
        check_etag(request, old)
        cur = {**old, **vals}
        if cur["status"] == "esperando" and not cur.get("requested_on"):
            vals["requested_on"] = today_gt()
        if cur["status"] == "resuelto" and not cur.get("resolved_on"):
            vals["resolved_on"] = today_gt()
        new = await db.patch(c, "external_item", eid, vals)
        if blocks is not None:
            await _set_blocks(c, eid, blocks)
        if old["status"] != new["status"]:
            await audit.write(c, user, "external", eid, new["project_id"],
                              [(f"Externo · {new['counterparty']}", EXTERNAL_STATUS[old["status"]], EXTERNAL_STATUS[new["status"]])])
        return (await _with_blocks(c, [new]))[0]


@router.post("/externals/{eid}/resolve", tags=["externals"])
async def resolve_external(eid: str, body: ResolveIn | None = None, user: dict = Depends(require_editor)):
    async with db.tx() as c:
        old = await db.get(c, "external_item", eid)
        if not old:
            raise HTTPException(404, "Pendiente no encontrado.")
        vals = {"status": "resuelto", "resolved_on": today_gt()}
        if body and body.response:
            vals["response"] = body.response
        new = await db.patch(c, "external_item", eid, vals)
        await audit.write(c, user, "external", eid, new["project_id"],
                          [(f"Externo · {new['counterparty']}", EXTERNAL_STATUS[old["status"]], "Resuelto")])
        return (await _with_blocks(c, [new]))[0]


@router.post("/externals/{eid}/follow-up", tags=["externals"])
async def follow_up_external(eid: str, user: dict = Depends(require_editor)):
    """'Ya lo solicité hoy' / 'Di seguimiento hoy': moves to esperando and schedules the next follow-up in 3 days."""
    async with db.tx() as c:
        old = await db.get(c, "external_item", eid)
        if not old:
            raise HTTPException(404, "Pendiente no encontrado.")
        today = today_gt()
        vals = {"follow_up_on": today + timedelta(days=3)}
        if old["status"] == "por_solicitar":
            vals.update(status="esperando", requested_on=today)
        new = await db.patch(c, "external_item", eid, vals)
        if old["status"] != new["status"]:
            await audit.write(c, user, "external", eid, new["project_id"],
                              [(f"Externo · {new['counterparty']}", EXTERNAL_STATUS[old["status"]], EXTERNAL_STATUS[new["status"]])])
        return (await _with_blocks(c, [new]))[0]


@router.delete("/externals/{eid}", status_code=204, tags=["externals"])
async def delete_external(eid: str, user: dict = Depends(require_editor)):
    async with db.tx() as c:
        if not await db.remove(c, "external_item", eid):
            raise HTTPException(404, "Pendiente no encontrado.")


# ------------------------------------------------------------------ workers
@router.get("/workers", tags=["staff"])
async def list_workers(_: dict = Depends(current_user)):
    t = db.T("worker")
    async with db.tx() as c:
        return await db.fetch(c, "worker", order=(t.c.role, t.c.name))


@router.post("/workers", status_code=201, tags=["staff"])
async def create_worker(body: WorkerIn, _: dict = Depends(require_editor)):
    async with db.tx() as c:
        return await db.create(c, "worker", body.model_dump())


@router.patch("/workers/{wid}", tags=["staff"])
async def update_worker(wid: str, body: WorkerPatch, _: dict = Depends(require_editor)):
    async with db.tx() as c:
        row = await db.patch(c, "worker", wid, body.model_dump(exclude_unset=True))
    if not row:
        raise HTTPException(404, "Trabajador no encontrado.")
    return row


@router.delete("/workers/{wid}", status_code=204, tags=["staff"])
async def delete_worker(wid: str, _: dict = Depends(require_editor)):
    t = db.T("assignment")
    async with db.tx() as c:
        if await db.fetch(c, "assignment", t.c.worker_id == wid, limit=1):
            raise HTTPException(409, "Primero elimina sus asignaciones.")
        if not await db.remove(c, "worker", wid):
            raise HTTPException(404, "Trabajador no encontrado.")


# ------------------------------------------------------------------ assignments
async def _overlap_message(c, worker_id, start: date, end: date | None, exclude_id=None) -> str:
    t = db.T("assignment")
    rows = await db.fetch(c, "assignment", t.c.worker_id == worker_id)
    end = end or start
    clash = [r for r in rows if str(r["id"]) != str(exclude_id) and r["start_date"] <= end and (r["end_date"] or r["start_date"]) >= start]
    parts = []
    for r in clash:
        p = await db.get(c, "project", r["project_id"])
        rng = fd(r["start_date"]) + (f" – {fd(r['end_date'])}" if r["end_date"] else "")
        parts.append(f"{(p or {}).get('short_name') or r['project_id']} ({rng})")
    return ("Conflicto: ya está asignado a " + ", ".join(parts) + ". Una persona no puede estar en dos ubicaciones el mismo día.") if parts else "Conflicto de fechas con otra asignación."


async def _validate_assignment(c, vals: dict, cur: dict):
    if cur.get("end_date") and cur["end_date"] < cur["start_date"]:
        raise HTTPException(422, '"Hasta" no puede ser anterior a "Desde".')
    if "project_id" in vals:
        await _need_project(c, vals["project_id"])
    if vals.get("activity_id"):
        vals["activity_id"] = vals["activity_id"].upper()
        if not await db.get(c, "activity", vals["activity_id"]):
            raise HTTPException(422, f"No existe la actividad {vals['activity_id']}.")
    if "worker_id" in vals and not await db.get(c, "worker", vals["worker_id"]):
        raise HTTPException(422, "El trabajador no existe.")


@router.get("/assignments", tags=["staff"])
async def list_assignments(project_id: str | None = None, from_: date | None = None, to: date | None = None, _: dict = Depends(current_user)):
    t = db.T("assignment")
    where = [t.c.project_id == project_id.upper()] if project_id else []
    async with db.tx() as c:
        rows = await db.fetch(c, "assignment", *where, order=t.c.start_date)
    if from_ or to:
        lo, hi = from_ or date.min, to or date.max
        rows = [r for r in rows if r["start_date"] <= hi and (r["end_date"] or r["start_date"]) >= lo]
    return rows


@router.post("/assignments", status_code=201, tags=["staff"])
async def create_assignment(body: AssignmentIn, user: dict = Depends(require_editor)):
    vals = body.model_dump()
    from sqlalchemy.exc import IntegrityError

    try:
        async with db.tx() as c:
            await _validate_assignment(c, vals, vals)
            return await db.create(c, "assignment", vals)
    except IntegrityError as e:
        if getattr(e.orig, "sqlstate", None) == "23P01":
            async with db.tx() as c:
                msg = await _overlap_message(c, vals["worker_id"], vals["start_date"], vals.get("end_date"))
            raise HTTPException(409, msg)
        raise


@router.patch("/assignments/{aid}", tags=["staff"])
async def update_assignment(aid: str, body: AssignmentPatch, user: dict = Depends(require_editor)):
    vals = body.model_dump(exclude_unset=True)
    from sqlalchemy.exc import IntegrityError

    try:
        async with db.tx() as c:
            old = await db.get(c, "assignment", aid)
            if not old:
                raise HTTPException(404, "Asignación no encontrada.")
            await _validate_assignment(c, vals, {**old, **vals})
            return await db.patch(c, "assignment", aid, vals)
    except IntegrityError as e:
        if getattr(e.orig, "sqlstate", None) == "23P01":
            cur = {**old, **vals}
            async with db.tx() as c:
                msg = await _overlap_message(c, cur["worker_id"], cur["start_date"], cur.get("end_date"), aid)
            raise HTTPException(409, msg)
        raise


@router.delete("/assignments/{aid}", status_code=204, tags=["staff"])
async def delete_assignment(aid: str, _: dict = Depends(require_editor)):
    async with db.tx() as c:
        if not await db.remove(c, "assignment", aid):
            raise HTTPException(404, "Asignación no encontrada.")


@router.get("/staffing/needs", tags=["staff"])
async def staffing_needs(as_of: date | None = None, _: dict = Depends(current_user)):
    async with db.tx() as c:
        m = await load_model(c, as_of)
    needs = m.staff_needs()
    active = [w for w in m.workers.values() if w["active"]]
    cap_t = sum(1 for w in active if w["role"] in ("tecnico", "supervisor"))
    cap_h = sum(1 for w in active if w["role"] == "ayudante")
    wins = [n for n in needs if n["window"]]
    peak_t = peak_h = 0
    peak_day = None
    for n in wins:
        d = n["window"]["start"]
        while d <= n["window"]["end"]:
            on = [y for y in wins if y["window"]["start"] <= d <= y["window"]["end"]]
            st = sum(y["required_technicians"] for y in on)
            if st > peak_t:
                peak_t, peak_h, peak_day = st, sum(y["required_helpers"] for y in on), d
            d += timedelta(days=1)
    return {
        "projects": needs,
        "capacity": {"technicians": cap_t, "helpers": cap_h},
        "if_all_overlap": {"technicians": sum(n["required_technicians"] for n in needs), "helpers": sum(n["required_helpers"] for n in needs)},
        "peak": {"technicians": peak_t, "helpers": peak_h, "day": peak_day} if peak_day else None,
    }


# ------------------------------------------------------------------ audit
@router.get("/audit", tags=["audit"])
async def audit_trail(entity: str | None = None, entity_id: str | None = None, project_id: str | None = None,
                      since: date | None = None, limit: int = 100, _: dict = Depends(current_user)):
    t = db.T("audit_log")
    where = []
    if entity:
        where.append(t.c.entity == entity)
    if entity_id:
        where.append(t.c.entity_id == entity_id)
    if project_id:
        where.append(t.c.project_id == project_id.upper())
    async with db.tx() as c:
        rows = await db.fetch(c, "audit_log", *where, order=t.c.ts.desc(), limit=max(1, min(limit, 500)))
    return [r for r in rows if not since or r["ts"].date() >= since]
