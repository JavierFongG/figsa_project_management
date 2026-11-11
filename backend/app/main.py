from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import db
from app.core.config import settings
from app.routers import activities, auth, budget, dashboard, misc, per_diems, projects, purchases, reports


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.jwt_secret in ("change-me", "") or len(settings.jwt_secret) < 32:
        import logging

        logging.getLogger("uvicorn.error").warning("JWT_SECRET is weak or default. Set a random string of 32+ characters.")
    await db.reflect()
    yield
    await db.engine.dispose()


app = FastAPI(title="FIGSA Centro de Control", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag"],
)

API = "/api/v1"
for r in (auth, projects, activities, dashboard, purchases, budget, per_diems, misc, reports):
    app.include_router(r.router, prefix=API)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    async with db.engine.connect() as c:
        await c.execute(text("select 1"))
    return {"ok": True}


@app.exception_handler(IntegrityError)
async def integrity_error(_: Request, exc: IntegrityError):
    code = getattr(exc.orig, "sqlstate", None)
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None) or ""
    if code == "23505":
        return JSONResponse({"detail": "Ya existe un registro con esos datos."}, status_code=409)
    if code == "23503":
        return JSONResponse({"detail": "Referencia inválida, o el registro está en uso por otros datos."}, status_code=409)
    if code == "23P01":
        return JSONResponse({"detail": "Conflicto de fechas con otro registro."}, status_code=409)
    if code == "23514":
        return JSONResponse({"detail": f"Valor fuera de rango ({constraint or 'restricción'})."}, status_code=422)
    return JSONResponse({"detail": "No se pudo guardar el cambio."}, status_code=400)
