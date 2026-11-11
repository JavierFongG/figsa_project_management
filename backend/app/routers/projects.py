from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core import db
from app.core.deps import check_etag, current_user, require_editor
from app.schemas import ProjectIn, ProjectPatch
from app.services import audit
from app.services.drive import extract_folder_id
from app.services.rules import nat_key

router = APIRouter(prefix="/projects", tags=["projects"])

TRACK = {"status": "Estado proyecto", "progress_pct": "Avance %", "priority": "Prioridad", "scenario_start": "Escenario", "exchange_rate": "Tipo de cambio"}


def _clean(vals: dict) -> dict:
    for k in ("drive_invoices_folder", "drive_receipts_folder"):
        if vals.get(k):
            vals[k] = extract_folder_id(vals[k])
    if vals.get("staffing_activity_id"):
        vals["staffing_activity_id"] = vals["staffing_activity_id"].upper()
    return vals


@router.get("")
async def list_projects(_: dict = Depends(current_user)):
    async with db.tx() as c:
        rows = await db.fetch(c, "project")
    return sorted(rows, key=lambda p: (p["sort_order"], nat_key(p["id"])))


@router.get("/{pid}")
async def get_project(pid: str, _: dict = Depends(current_user)):
    async with db.tx() as c:
        p = await db.get(c, "project", pid.upper())
    if not p:
        raise HTTPException(404, "Proyecto no encontrado.")
    return p


@router.post("", status_code=201)
async def create_project(body: ProjectIn, user: dict = Depends(require_editor)):
    vals = _clean(body.model_dump())
    async with db.tx() as c:
        if await db.get(c, "project", vals["id"]):
            raise HTTPException(409, f"Ya existe el proyecto {vals['id']}.")
        row = await db.create(c, "project", vals)
        await audit.write(c, user, "project", row["id"], row["id"], [("Proyecto creado", None, row["name"])])
    return row


@router.patch("/{pid}")
async def update_project(pid: str, body: ProjectPatch, request: Request, user: dict = Depends(require_editor)):
    pid = pid.upper()
    vals = _clean(body.model_dump(exclude_unset=True))
    vals.pop("id", None)
    async with db.tx() as c:
        old = await db.get(c, "project", pid)
        if not old:
            raise HTTPException(404, "Proyecto no encontrado.")
        check_etag(request, old)
        if vals.get("staffing_activity_id") and not await db.get(c, "activity", vals["staffing_activity_id"]):
            raise HTTPException(422, f"No existe la actividad {vals['staffing_activity_id']}.")
        row = await db.patch(c, "project", pid, vals)
        await audit.write(c, user, "project", pid, pid, audit.diff(old, row, TRACK))
    return row
