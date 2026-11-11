"""Upload invoices and receipts to Google Drive.

Two credential modes:
1. OAuth refresh token of a real Google account (works with personal Gmail and Workspace). Files are owned by that account.
2. Service account JSON (raw JSON or base64). Needs a *Shared Drive*, because service accounts have no storage quota of their own.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import re

from app.core.config import settings

SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def extract_folder_id(value: str | None) -> str | None:
    if not value:
        return None
    m = re.search(r"folders/([A-Za-z0-9_-]+)", value)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([A-Za-z0-9_-]+)", value)
    return m.group(1) if m else value.strip()


def configured() -> bool:
    return bool(settings.google_service_account_json or (settings.google_client_id and settings.google_client_secret and settings.google_refresh_token))


def _credentials():
    if settings.google_service_account_json:
        from google.oauth2 import service_account

        raw = settings.google_service_account_json.strip()
        if not raw.startswith("{"):
            raw = base64.b64decode(raw).decode()
        return service_account.Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    from google.oauth2.credentials import Credentials

    return Credentials(
        None,
        refresh_token=settings.google_refresh_token,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )


def _upload_sync(folder_id: str, name: str, data: bytes, mime: str) -> dict:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseUpload

    try:
        service = build("drive", "v3", credentials=_credentials(), cache_discovery=False)
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime or "application/octet-stream", resumable=False)
        f = service.files().create(
            body={"name": name, "parents": [folder_id]}, media_body=media, fields="id,webViewLink", supportsAllDrives=True
        ).execute()
        return {"id": f.get("id"), "url": f.get("webViewLink") or f"https://drive.google.com/file/d/{f.get('id')}/view"}
    except HttpError as e:
        status = getattr(e.resp, "status", None)
        if status == 404:
            raise DriveError("folder_not_found", "No se encontró la carpeta de Drive o la cuenta conectada no tiene acceso.")
        if status in (401, 403):
            raise DriveError("no_access", "Google rechazó el acceso a Drive. Revisa los permisos de la cuenta conectada.")
        raise DriveError("drive_error", f"Drive respondió con un error ({status}).")
    except Exception as e:  # token revoked, network, bad credentials
        raise DriveError("drive_error", f"No se pudo subir a Drive: {type(e).__name__}.")


async def upload(folder: str | None, name: str, data: bytes, mime: str) -> dict:
    folder_id = extract_folder_id(folder)
    if not folder_id:
        raise DriveError("no_folder", "Este proyecto no tiene carpeta de Drive configurada. Agrégala en Editar proyecto.")
    if not configured():
        raise DriveError("not_configured", "Google Drive no está configurado en el servidor.")
    return await asyncio.to_thread(_upload_sync, folder_id, name, data, mime)
