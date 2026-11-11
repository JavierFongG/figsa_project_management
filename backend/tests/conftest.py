import os
import subprocess
import sys
from pathlib import Path

import pytest

# Tests need a throwaway Postgres: TEST_DATABASE_URL=postgresql://user:pass@host:5432/figsa_test
TEST_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@localhost:5433/figsa_test")
os.environ["DATABASE_URL"] = TEST_URL
os.environ["MIGRATION_DATABASE_URL"] = ""
os.environ["JWT_SECRET"] = "test-secret"

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    """Rebuild the schema from scratch with the real Alembic migration."""
    env = {**os.environ}
    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], cwd=ROOT, env=env, check=False, capture_output=True)
    res = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    yield


@pytest.fixture(scope="session")
async def client(migrated_db):
    import httpx
    from app.core import db
    from app.core.security import hash_password
    from app.main import app

    await db.reflect()
    async with db.tx() as c:
        await db.create(c, "app_user", {"email": "editor@test.com", "name": "Editor", "role": "editor", "password_hash": hash_password("editor-password-1")})
        await db.create(c, "app_user", {"email": "viewer@test.com", "name": "Viewer", "role": "viewer", "password_hash": hash_password("viewer-password-1")})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as cl:
        yield cl


async def _login(client, email, password):
    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture(scope="session")
async def editor(client):
    return await _login(client, "editor@test.com", "editor-password-1")


@pytest.fixture(scope="session")
async def viewer(client):
    return await _login(client, "viewer@test.com", "viewer-password-1")
