from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt

from app.core.security import read_token

bearer = HTTPBearer(auto_error=False)


async def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicia sesión para continuar.")
    try:
        data = read_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "La sesión expiró. Vuelve a iniciar sesión.")
    return {"id": data["sub"], "email": data["email"], "name": data["name"], "role": data["role"]}


async def require_editor(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "editor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu usuario es de solo lectura.")
    return user


def check_etag(request: Request, row: dict, field: str = "updated_at") -> None:
    """Optimistic concurrency: if the client sent If-Match, it must equal the row's current updated_at."""
    sent = request.headers.get("if-match")
    if not sent or row.get(field) is None:
        return
    if sent.strip('"') != row[field].isoformat():
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            "Este registro cambió mientras lo editabas. Recarga e intenta de nuevo.",
        )
