import re

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from app.core import db
from app.core.config import settings
from app.core.deps import check_etag, current_user, require_editor
from app.schemas import PurchaseIn, PurchasePatch
from app.services import audit, drive
from app.services.snapshot import today_gt

router = APIRouter(prefix="/purchases", tags=["purchases"])

TRACK = {
    "status": "Estado compra", "invoice_mode": "Factura", "budget_line_id": "Rubro", "advance_paid": "Anticipo pagado",
    "total_amount": "Monto total", "received_on": "Recepción",
}
DONE = ("realizada", "recibida")


async def _attach_files(c, rows: list[dict]) -> list[dict]:
    files = await db.fetch(c, "purchase_file")
    by: dict = {}
    for f in files:
        by.setdefault(f["purchase_id"], {})[f["kind"]] = f
    for r in rows:
        r["files"] = by.get(r["id"], {})
    return rows


async def _validate(c, vals: dict, current: dict | None) -> dict:
    cur = {**(current or {}), **vals}
    if "project_id" in vals and not await db.get(c, "project", vals["project_id"]):
        raise HTTPException(422, f"No existe el proyecto {vals['project_id']}.")
    if vals.get("activity_id"):
        vals["activity_id"] = vals["activity_id"].upper()
        if not await db.get(c, "activity", vals["activity_id"]):
            raise HTTPException(422, f"No existe la actividad {vals['activity_id']}.")
    if vals.get("budget_line_id"):
        bl = await db.get(c, "budget_line", vals["budget_line_id"])
        if not bl:
            raise HTTPException(422, "El rubro del presupuesto no existe.")
        if bl["project_id"] != cur["project_id"]:
            raise HTTPException(422, f"La línea {bl['code']} es del proyecto {bl['project_id']}. Cambia el proyecto o el rubro.")
    # entering/leaving done state sets the completion date
    was_done = bool(current) and current["status"] in DONE
    now_done = cur["status"] in DONE
    if now_done and not was_done:
        vals["completed_on"] = today_gt()
    elif was_done and not now_done:
        vals["completed_on"] = None
    return vals


@router.get("")
async def list_purchases(project_id: str | None = None, status: str | None = None, _: dict = Depends(current_user)):
    t = db.T("purchase")
    where = []
    if project_id:
        where.append(t.c.project_id == project_id.upper())
    if status:
        where.append(t.c.status == status)
    async with db.tx() as c:
        rows = await db.fetch(c, "purchase", *where, order=(t.c.project_id, t.c.created_at))
        return await _attach_files(c, rows)


@router.get("/{pid}")
async def get_purchase(pid: str, _: dict = Depends(current_user)):
    async with db.tx() as c:
        row = await db.get(c, "purchase", pid)
        if not row:
            raise HTTPException(404, "Compra no encontrada.")
        return (await _attach_files(c, [row]))[0]


@router.post("", status_code=201)
async def create_purchase(body: PurchaseIn, user: dict = Depends(require_editor)):
    vals = body.model_dump()
    async with db.tx() as c:
        vals = await _validate(c, vals, None)
        row = await db.create(c, "purchase", vals)
        await audit.write(c, user, "purchase", row["id"], row["project_id"], [("Compra creada", None, row["product"])])
        return (await _attach_files(c, [row]))[0]


@router.patch("/{pid}")
async def update_purchase(pid: str, body: PurchasePatch, request: Request, user: dict = Depends(require_editor)):
    vals = body.model_dump(exclude_unset=True)
    async with db.tx() as c:
        old = await db.get(c, "purchase", pid)
        if not old:
            raise HTTPException(404, "Compra no encontrada.")
        check_etag(request, old)
        vals = await _validate(c, vals, old)
        new = await db.patch(c, "purchase", pid, vals)
        ch = [(f"{lab} · {new['product']}", b, a) for lab, b, a in audit.diff(old, new, TRACK)]
        await audit.write(c, user, "purchase", pid, new["project_id"], ch)
        return (await _attach_files(c, [new]))[0]


@router.delete("/{pid}", status_code=204)
async def delete_purchase(pid: str, user: dict = Depends(require_editor)):
    async with db.tx() as c:
        old = await db.get(c, "purchase", pid)
        if not old:
            raise HTTPException(404, "Compra no encontrada.")
        await db.remove(c, "purchase", pid)
        await audit.write(c, user, "purchase", pid, old["project_id"], [("Compra eliminada", old["product"], None)])


@router.post("/{pid}/files", status_code=201)
async def upload_file(pid: str, kind: str = Query(pattern="^(factura|comprobante)$"), file: UploadFile = File(...), user: dict = Depends(require_editor)):
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"El archivo supera {settings.max_upload_mb} MB.")
    if not data:
        raise HTTPException(422, "El archivo está vacío.")
    async with db.tx() as c:
        p = await db.get(c, "purchase", pid)
        if not p:
            raise HTTPException(404, "Compra no encontrada.")
        proj = await db.get(c, "project", p["project_id"])
    folder = proj["drive_invoices_folder"] if kind == "factura" else proj["drive_receipts_folder"]
    label = "Factura" if kind == "factura" else "Comprobante"
    product = re.sub(r'[\\/:*?"<>|]+', " ", p["product"] or "Gasto")[:60]
    inv = f" {p['invoice_no']}" if kind == "factura" and p.get("invoice_no") else ""
    name = f"{today_gt().isoformat()} - {product} - {label}{inv} - {file.filename}"
    try:
        up = await drive.upload(folder, name, data, file.content_type or "application/octet-stream")
    except drive.DriveError as e:
        raise HTTPException(502 if e.code in ("drive_error", "no_access", "folder_not_found") else 422, e.message)
    t = db.T("purchase_file")
    async with db.tx() as c:
        await c.execute(t.delete().where((t.c.purchase_id == p["id"]) & (t.c.kind == kind)))
        row = await db.create(c, "purchase_file", {
            "purchase_id": p["id"], "kind": kind, "filename": file.filename or "archivo", "size_bytes": len(data),
            "mime_type": file.content_type, "drive_id": up["id"], "url": up["url"], "uploaded_by": user["id"],
        })
        await audit.write(c, user, "purchase", p["id"], p["project_id"], [(f"{label} · {p['product']}", None, file.filename)])
    return row


@router.delete("/{pid}/files/{kind}", status_code=204)
async def delete_file(pid: str, kind: str, user: dict = Depends(require_editor)):
    if kind not in ("factura", "comprobante"):
        raise HTTPException(422, "Tipo de archivo inválido.")
    t = db.T("purchase_file")
    async with db.tx() as c:
        p = await db.get(c, "purchase", pid)
        if not p:
            raise HTTPException(404, "Compra no encontrada.")
        res = await c.execute(t.delete().where((t.c.purchase_id == p["id"]) & (t.c.kind == kind)).returning(t.c.filename))
        old = res.first()
        if old:
            await audit.write(c, user, "purchase", p["id"], p["project_id"],
                              [(f"{'Factura' if kind == 'factura' else 'Comprobante'} quitado · {p['product']}", old[0], None)])
