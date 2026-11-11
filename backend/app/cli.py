"""Admin commands (there is no user-management API; two users are created from here).

  python -m app.cli create-user --email ana@figsa.com --name "Ana" --role editor
  python -m app.cli create-user --email jefe@figsa.com --name "Jefe" --role viewer
  python -m app.cli set-password --email ana@figsa.com
  python -m app.cli list-users
"""
import argparse
import asyncio
import getpass
import sys

from app.core import db
from app.core.security import hash_password


async def create_user(email: str, name: str, role: str, password: str | None):
    password = password or getpass.getpass("Contraseña (mínimo 10 caracteres): ")
    if len(password) < 10:
        sys.exit("La contraseña debe tener al menos 10 caracteres.")
    await db.reflect()
    email = email.strip().lower()
    async with db.tx() as c:
        if await db.fetch(c, "app_user", db.T("app_user").c.email == email):
            sys.exit(f"Ya existe un usuario con {email}. Usa set-password para cambiar la contraseña.")
        await db.create(c, "app_user", {"email": email, "name": name, "role": role, "password_hash": hash_password(password)})
    print(f"Usuario creado: {email} ({role})")
    await db.engine.dispose()


async def set_password(email: str, password: str | None):
    password = password or getpass.getpass("Nueva contraseña (mínimo 10 caracteres): ")
    if len(password) < 10:
        sys.exit("La contraseña debe tener al menos 10 caracteres.")
    await db.reflect()
    t = db.T("app_user")
    async with db.tx() as c:
        rows = await db.fetch(c, "app_user", t.c.email == email.strip().lower())
        if not rows:
            sys.exit("No existe ese usuario.")
        await db.patch(c, "app_user", rows[0]["id"], {"password_hash": hash_password(password)})
    print("Contraseña actualizada.")
    await db.engine.dispose()


async def list_users():
    await db.reflect()
    async with db.tx() as c:
        for u in await db.fetch(c, "app_user", order=db.T("app_user").c.email):
            print(f"{u['email']:40} {u['role']:8} {'activo' if u['active'] else 'inactivo'}  {u['name']}")
    await db.engine.dispose()


def main():
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    cu = sub.add_parser("create-user")
    cu.add_argument("--email", required=True)
    cu.add_argument("--name", required=True)
    cu.add_argument("--role", choices=["viewer", "editor"], required=True)
    cu.add_argument("--password")
    sp = sub.add_parser("set-password")
    sp.add_argument("--email", required=True)
    sp.add_argument("--password")
    sub.add_parser("list-users")
    a = p.parse_args()
    if a.cmd == "create-user":
        asyncio.run(create_user(a.email, a.name, a.role, a.password))
    elif a.cmd == "set-password":
        asyncio.run(set_password(a.email, a.password))
    else:
        asyncio.run(list_users())


if __name__ == "__main__":
    main()
