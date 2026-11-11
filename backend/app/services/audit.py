from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.services.labels import label


def _s(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return "Sí" if v else "No"
    return label(v) if isinstance(v, str) else str(v)


def diff(old: dict | None, new: dict, fields: dict[str, str]) -> list[tuple[str, str | None, str | None]]:
    """Changes in tracked fields as (label, before, after). `old=None` means the record is new (not diffed)."""
    out = []
    if old is None:
        return out
    for key, lab in fields.items():
        if key not in new:
            continue
        b, a = old.get(key), new.get(key)
        if str(b) != str(a):
            out.append((lab, _s(b), _s(a)))
    return out


async def write(conn: AsyncConnection, user: dict | None, entity: str, entity_id, project_id: str | None,
                changes: Iterable[tuple[str, str | None, str | None]]) -> None:
    for field, before, after in changes:
        await db.create(conn, "audit_log", {
            "user_id": user["id"] if user else None,
            "entity": entity,
            "entity_id": str(entity_id),
            "project_id": project_id,
            "field": field,
            "before_value": before,
            "after_value": after,
        })
