from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core import db
from app.core.deps import check_etag, current_user, require_editor
from app.schemas import PerDiemIn, PerDiemPatch
from app.services import audit
from app.services.labels import PER_DIEM_CATEGORY, fdy, money
from app.services.rules import nat_key

router = APIRouter(prefix="/per-diems", tags=["per-diems"])


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
    if cur.get("kind") == "anticipo":
        vals["budget_line_id"] = None  # advances are not spending
    return vals


def _in_month(d: date, month: str | None) -> bool:
    return not month or d.strftime("%Y-%m") == month


@router.get("")
async def list_per_diems(project_id: str | None = None, month: str | None = None, person: str | None = None, _: dict = Depends(current_user)):
    t = db.T("per_diem")
    where = [t.c.project_id == project_id.upper()] if project_id else []
    async with db.tx() as c:
        rows = await db.fetch(c, "per_diem", *where, order=(t.c.entry_date.desc(), t.c.created_at.desc()))
    return [r for r in rows if _in_month(r["entry_date"], month) and (not person or r["person"].lower() == person.lower())]


@router.get("/summary")
async def summary(project_id: str | None = None, month: str | None = None, _: dict = Depends(current_user)):
    """Settlement ("liquidación"): per person advances vs expenses, per project by category, plus copyable text."""
    t = db.T("per_diem")
    where = [t.c.project_id == project_id.upper()] if project_id else []
    async with db.tx() as c:
        rows = [r for r in await db.fetch(c, "per_diem", *where) if _in_month(r["entry_date"], month)]
        projects = {p["id"]: p for p in await db.fetch(c, "project")}
    people: dict[str, dict] = {}
    for r in rows:
        p = people.setdefault((r["person"] or "Sin asignar").strip(), {"person": r["person"], "advances": 0.0, "expenses": 0.0, "pending": 0.0})
        a = float(r["amount"])
        if r["kind"] == "anticipo":
            p["advances"] += a
        else:
            p["expenses"] += a
            if r["status"] == "pendiente":
                p["pending"] += a
    for p in people.values():
        bal = p["advances"] - p["expenses"]
        p["balance"] = bal  # >0 person returns money, <0 reimburse
    gastos = [r for r in rows if r["kind"] == "gasto"]
    by_project: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "categories": defaultdict(float)})
    for r in gastos:
        bp = by_project[r["project_id"]]
        bp["total"] += float(r["amount"])
        bp["categories"][r.get("category") or "otros"] += float(r["amount"])
    no_receipt = [r for r in gastos if r.get("receipt_type") == "ninguno"]

    scope = (projects[project_id.upper()].get("short_name") or project_id.upper()) if project_id and project_id.upper() in projects else "Todos los proyectos"
    if month:
        scope += f" · {month}"
    lines = [f"LIQUIDACIÓN DE VIÁTICOS — {scope}", f"Generado: {fdy(date.today())}", ""]
    for pid in sorted(by_project, key=nat_key):
        pr = projects.get(pid, {})
        lines.append((pr.get("short_name") or pr.get("name") or pid).upper())
        for k, lab in PER_DIEM_CATEGORY.items():
            v = by_project[pid]["categories"].get(k)
            if v:
                lines.append(f"  {lab}: {money(v)}")
        lines += [f"  Total: {money(by_project[pid]['total'])}", ""]
    lines.append("POR PERSONA")
    for name in sorted(people, key=str.lower):
        p = people[name]
        tail = f"devuelve {money(p['balance'])}" if p["balance"] > 0 else f"reembolsar {money(-p['balance'])}" if p["balance"] < 0 else "cuadrado"
        lines.append(f"  {p['person']}: anticipos {money(p['advances'])} · gastos {money(p['expenses'])} · {tail}")
    if no_receipt:
        lines += ["", f"Gastos sin comprobante: {len(no_receipt)} por {money(sum(float(r['amount']) for r in no_receipt))}"]
    return {
        "people": sorted(people.values(), key=lambda p: p["person"].lower()),
        "projects": [{"project_id": pid, "total": v["total"], "categories": dict(v["categories"])} for pid, v in by_project.items()],
        "without_receipt": {"count": len(no_receipt), "amount": sum(float(r["amount"]) for r in no_receipt)},
        "text": "\n".join(lines),
    }


@router.post("", status_code=201)
async def create_per_diem(body: PerDiemIn, user: dict = Depends(require_editor)):
    vals = body.model_dump()
    async with db.tx() as c:
        vals = await _validate(c, vals, None)
        row = await db.create(c, "per_diem", vals)
        what = "Anticipo viáticos" if row["kind"] == "anticipo" else "Viático"
        await audit.write(c, user, "per_diem", row["id"], row["project_id"], [(f"{what} · {row['person']}", None, money(row["amount"]))])
    return row


@router.patch("/{rid}")
async def update_per_diem(rid: str, body: PerDiemPatch, request: Request, user: dict = Depends(require_editor)):
    vals = body.model_dump(exclude_unset=True)
    async with db.tx() as c:
        old = await db.get(c, "per_diem", rid)
        if not old:
            raise HTTPException(404, "Registro no encontrado.")
        check_etag(request, old)
        vals = await _validate(c, vals, old)
        new = await db.patch(c, "per_diem", rid, vals)
        if str(old["amount"]) != str(new["amount"]):
            await audit.write(c, user, "per_diem", rid, new["project_id"], [(f"Viático · {new['person']}", money(old["amount"]), money(new["amount"]))])
    return new


@router.delete("/{rid}", status_code=204)
async def delete_per_diem(rid: str, user: dict = Depends(require_editor)):
    async with db.tx() as c:
        old = await db.get(c, "per_diem", rid)
        if not old:
            raise HTTPException(404, "Registro no encontrado.")
        await db.remove(c, "per_diem", rid)
        await audit.write(c, user, "per_diem", rid, old["project_id"], [(f"Viático eliminado · {old['person']}", money(old["amount"]), None)])
