"""Async engine plus thin CRUD helpers over reflected tables (SQLAlchemy Core).

The schema is owned by Alembic (alembic/versions). At startup we reflect it so routers can use
plain dict rows instead of duplicating every table as an ORM class.
"""
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import MetaData, delete as sa_delete, insert as sa_insert, select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import settings

# prepare_threshold=None: no server-side prepared statements, safe behind Neon's pgbouncer pooler.
engine = create_async_engine(
    settings.sqlalchemy_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_recycle=300,
    connect_args={"prepare_threshold": None},
)
metadata = MetaData()


async def reflect() -> None:
    async with engine.connect() as conn:
        await conn.run_sync(metadata.reflect)


@asynccontextmanager
async def tx():
    """One transaction per request handler: commits on success, rolls back on any exception."""
    async with engine.begin() as conn:
        yield conn


def T(name: str):
    return metadata.tables[name]


def _rows(result) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in result]


async def fetch(conn: AsyncConnection, name: str, *where, order=None, limit: int | None = None, offset: int | None = None):
    q = select(T(name))
    for w in where:
        q = q.where(w)
    if order is not None:
        q = q.order_by(*order) if isinstance(order, (list, tuple)) else q.order_by(order)
    if limit is not None:
        q = q.limit(limit)
    if offset:
        q = q.offset(offset)
    return _rows(await conn.execute(q))


async def get(conn: AsyncConnection, name: str, key: Any, pk: str = "id") -> dict | None:
    t = T(name)
    rows = _rows(await conn.execute(select(t).where(t.c[pk] == key)))
    return rows[0] if rows else None


async def create(conn: AsyncConnection, name: str, values: dict) -> dict:
    t = T(name)
    res = await conn.execute(sa_insert(t).values(**values).returning(t))
    return _rows(res)[0]


async def patch(conn: AsyncConnection, name: str, key: Any, values: dict, pk: str = "id") -> dict | None:
    t = T(name)
    if not values:
        return await get(conn, name, key, pk)
    res = await conn.execute(sa_update(t).where(t.c[pk] == key).values(**values).returning(t))
    rows = _rows(res)
    return rows[0] if rows else None


async def remove(conn: AsyncConnection, name: str, key: Any, pk: str = "id") -> bool:
    t = T(name)
    res = await conn.execute(sa_delete(t).where(t.c[pk] == key))
    return res.rowcount > 0
