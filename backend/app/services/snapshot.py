from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import db
from app.core.config import settings
from app.services.rules import Model


def today_gt(as_of: date | None = None) -> date:
    """'Today' in the company's time zone (America/Guatemala, UTC-6, no DST)."""
    return as_of or datetime.now(ZoneInfo(settings.tz)).date()


async def load_model(conn: AsyncConnection, as_of: date | None = None) -> Model:
    projects = await db.fetch(conn, "project", order=db.T("project").c.sort_order)
    return Model(
        projects=projects,
        activities=await db.fetch(conn, "activity"),
        dependencies=await db.fetch(conn, "activity_dependency"),
        externals=await db.fetch(conn, "external_item"),
        ext_blocks=await db.fetch(conn, "external_item_blocks"),
        purchases=await db.fetch(conn, "purchase"),
        assignments=await db.fetch(conn, "assignment"),
        workers=await db.fetch(conn, "worker"),
        today=today_gt(as_of),
    )


async def note_stats(conn: AsyncConnection) -> dict[str, dict]:
    """Last note and note count per activity."""
    rows = await db.fetch(conn, "activity_note", order=db.T("activity_note").c.created_at)
    out: dict[str, dict] = {}
    for r in rows:
        s = out.setdefault(r["activity_id"], {"count": 0, "last": None})
        s["count"] += 1
        s["last"] = {"id": r["id"], "body": r["body"], "created_at": r["created_at"]}
    return out
