from fastapi import APIRouter, Depends, HTTPException

from app.core import db
from app.core.deps import current_user
from app.core.security import make_token, verify_password
from app.schemas import LoginIn

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginIn):
    async with db.tx() as c:
        t = db.T("app_user")
        rows = await db.fetch(c, "app_user", t.c.email == body.email.strip().lower())
    user = rows[0] if rows else None
    # Same message for unknown user and wrong password.
    if not user or not user["active"] or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Correo o contraseña incorrectos.")
    return {
        "access_token": make_token(user),
        "token_type": "bearer",
        "user": {"id": str(user["id"]), "email": user["email"], "name": user["name"], "role": user["role"]},
    }


@router.get("/me")
async def me(user: dict = Depends(current_user)):
    return {**user, "can_write": user["role"] == "editor"}
