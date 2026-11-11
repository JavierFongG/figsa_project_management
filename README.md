# FIGSA · Centro de Control

Project-management tool for FIGSA: portfolio, tasks, Gantt schedule, purchases and payments, budget vs. executed, per-diems, external dependencies, staffing and shareable reports.

| Layer | Tech | Folder |
|---|---|---|
| Database | PostgreSQL 16 (Neon in production) | `backend/alembic/versions/` |
| Backend | FastAPI, SQLAlchemy Core (async), Alembic, JWT | `backend/` |
| Frontend | React 18 + TypeScript + Vite | `frontend/` |
| Hosting | Fly.io (two apps) + Neon + Google Drive for invoices | `deployment.md` |

All business rules (schedule projection, status, critical path, priorities, finance totals, staffing needs) run **on the server**; the UI only renders what the API returns.

**Deploying to the cloud from scratch:** read [`deployment.md`](deployment.md).

## Run it locally

Requirements: Python 3.12, Node 20, PostgreSQL 16 (or a free Neon database).

```bash
# 1. Database
createdb figsa            # or use a Neon connection string

# 2. Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env      # edit DATABASE_URL and JWT_SECRET
alembic upgrade head
python -m app.cli create-user --email you@example.com --name "You" --role editor
python -m app.cli create-user --email viewer@example.com --name "Viewer" --role viewer
uvicorn app.main:app --reload          # http://localhost:8000/docs

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                            # http://localhost:5173 (proxies /api to :8000)
```

## Tests

```bash
cd backend
createdb figsa_test
TEST_DATABASE_URL=postgresql://localhost/figsa_test pytest     # rebuilds the schema on every run; use a throwaway DB
cd ../frontend && npm run build        # type-checks and builds
```

## Roles

* `editor`: creates, edits and deletes everything.
* `viewer`: read-only (enforced by the API, not just hidden in the UI).

Users are created only from the command line (`python -m app.cli create-user | set-password | list-users`).

## API

Interactive docs at `/docs` on the backend. Everything is under `/api/v1`; protected routes need `Authorization: Bearer <token>` from `POST /api/v1/auth/login`. Updates accept an optional `If-Match: <updated_at>` header; a stale value returns `412`.
