# Deployment guide — FIGSA Centro de Control

This guide takes you from **nothing** to a running system on the internet, assuming you have no accounts and no services created yet. Follow the steps in order. Every command is meant to be copied as-is; anything in `UPPER_CASE_WITH_UNDERSCORES` is a value you replace.

**What you will end up with**

```
 Browser ──► figsa-web.fly.dev   (Fly.io app #1: React site served by nginx)
    │
    └──────► figsa-api.fly.dev   (Fly.io app #2: FastAPI backend)
                 │        │
                 │        └──► Google Drive   (invoices and receipts, via your Google account)
                 └───────────► Neon           (PostgreSQL database)
```

**Time:** about 60–90 minutes the first time (most of it is Google setup).
**Cost:** Neon has a free plan. Fly.io requires a credit card and bills for what you use; this setup (one 512 MB machine kept running for the API, one 256 MB machine for the site that sleeps when idle) is typically a few US dollars per month. Prices change, so check <https://fly.io/docs/about/pricing/> and <https://neon.com/pricing> before you start.

**Things you will need to keep safe** (a password manager is ideal): the Neon connection strings, the JWT secret, the Google client secret and refresh token, and the two users' passwords. Never commit them to git.

---

## 0. Before you start

### 0.1 Accounts to create

| Service | Used for | Sign up at | Notes |
|---|---|---|---|
| GitHub | Your code (already exists) | <https://github.com> | The repo is already connected. |
| Neon | Database | <https://neon.com> | "Sign up" → continue with GitHub or Google. No card needed for the free plan. |
| Fly.io | Hosts the backend and the frontend | <https://fly.io> | Needs a credit card to deploy. |
| Google | Drive storage for invoices | <https://console.cloud.google.com> | Use the **same Google account that owns the Drive folders**. |

### 0.2 Tools to install on your Mac

Open the **Terminal** app and run:

```bash
# Homebrew (skip if `brew --version` already works)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install flyctl          # the Fly.io command-line tool
brew install python@3.12     # only needed once, for the Google token script in step 3
```

Check them:

```bash
fly version
python3.12 --version
openssl version
git --version
```

### 0.3 Get the code

```bash
cd /Users/javi/Documents/wais/figsa/project_management/figsa_project_management
git status
```

You should see the `backend/`, `frontend/`, `deployment.md` files here. The rest of the guide assumes you are in this folder, which we'll call **the repo root**.

---

## 1. Create the database (Neon)

1. Go to <https://console.neon.tech> and sign in.
2. Click **Create project** (or **New project**).
   - **Project name:** `figsa`
   - **Postgres version:** `16` (17 also works)
   - **Cloud / Region:** `AWS` → `US East 1 (N. Virginia)`. This is the closest region to Fly's `iad` (Ashburn), which this guide uses. Keeping them close makes every request faster.
   - Click **Create**.
3. Neon opens a **Connect** panel (if not, click the **Connect** button on the project dashboard). Leave **Branch** = `main`, **Database** = `neondb`, **Role** = the default one.
4. You need **two** connection strings. Copy both into a scratch file (you'll paste them in step 5):

   | Name in this guide | How to get it |
   |---|---|
   | **`POOLED_URL`** | Make sure the **Connection pooling** toggle is **ON**. Copy the string. The host contains `-pooler`, e.g. `postgresql://neondb_owner:PASSWORD@ep-xxxx-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require` |
   | **`DIRECT_URL`** | Turn the **Connection pooling** toggle **OFF**. Copy the string. The host has **no** `-pooler`, e.g. `postgresql://neondb_owner:PASSWORD@ep-xxxx.us-east-1.aws.neon.tech/neondb?sslmode=require` |

   If Neon shows the password hidden, click **Show password** before copying. Keep any extra parameters (like `&channel_binding=require`) exactly as Neon gives them.

   **Why two?** The app uses the pooled one (handles many connections cheaply). Database migrations use the direct one (migrations need a normal session).

5. You do **not** need to create tables. The backend creates them automatically on first deploy (step 6).

> Neon's free plan puts the database to sleep after a few minutes of inactivity. The first request after that can take a couple of seconds longer. The backend is configured to reconnect automatically.

---

## 2. Generate the secret that signs logins

In Terminal:

```bash
openssl rand -hex 32
```

Copy the 64-character result. This is your **`JWT_SECRET`**. Anyone who knows it can forge logins, so never share it. If you ever change it, everyone is simply logged out.

---

## 3. Google Drive (for invoices and receipts)

This step lets the backend upload files into folders in **your** Google Drive. You can skip it now and come back later: everything else works, and uploading a file will show a message saying Drive is not configured.

### 3.1 Create the Drive folders

In <https://drive.google.com>, for each project create (or pick) two folders, for example `FIGSA / CEM / Facturas` and `FIGSA / CEM / Comprobantes`. Open each folder and copy its URL from the address bar (it looks like `https://drive.google.com/drive/folders/1AbCdEf...`). You will paste these URLs into each project inside the app later ("Carpeta de Drive").

### 3.2 Create a Google Cloud project

1. Go to <https://console.cloud.google.com> and sign in with the Google account that owns the folders. Accept the terms if asked.
2. Top bar → project picker → **New project**. Name: `figsa`. Click **Create**, then select it in the picker.

### 3.3 Enable the Drive API

1. Left menu → **APIs & Services** → **Library**.
2. Search `Google Drive API` → open it → **Enable**.

### 3.4 Configure the consent screen

1. **APIs & Services** → **OAuth consent screen** (in newer consoles this is **Google Auth Platform** → **Branding / Audience**).
2. If asked for a user type, choose **External** → **Create**.
3. Fill: **App name** `FIGSA`, **User support email** = your email, **Developer contact email** = your email. Save.
4. **Scopes**: you can leave the list empty (the script requests Drive access itself).
5. **Publish the app to production** (important): on the **Audience** page (or the consent screen page) click **Publish app** → **Confirm**.
   - *Why:* apps left in "Testing" make Google **expire the refresh token after 7 days**, and uploads would break a week after deploying.
   - Google will say the app is "unverified". That is fine for a private tool used by one account: you will see a warning screen once in step 3.6 (click **Advanced** → **Go to FIGSA (unsafe)**). You do not need to submit it for verification.

### 3.5 Create the OAuth client

1. **APIs & Services** → **Credentials** → **Create credentials** → **OAuth client ID**.
2. **Application type:** `Desktop app`. **Name:** `figsa-backend`. **Create**.
3. A dialog shows the **Client ID** (ends in `.apps.googleusercontent.com`) and **Client secret**. Copy both.

### 3.6 Get the refresh token (runs on your Mac)

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install google-auth-oauthlib
python scripts/google_auth.py --client-id "YOUR_CLIENT_ID" --client-secret "YOUR_CLIENT_SECRET"
```

A browser window opens:
1. Pick the Google account that owns the folders.
2. On "Google hasn't verified this app": click **Advanced** → **Go to FIGSA (unsafe)**.
3. Tick the Drive permission box and click **Continue**.

The terminal then prints:

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
```

Keep these three values for step 5. Then clean up:

```bash
deactivate
cd ..
```

> The backend can only see and write files that its Google account can access. If you later move the folders to another Google account, run this step again with that account.

---

## 4. Log in to Fly.io

```bash
fly auth signup      # first time only; opens the browser. If you already have an account: fly auth login
fly auth whoami      # should print your email
```

If you have not added a credit card yet, open <https://fly.io/dashboard> → **Billing** and add one. Deploys fail without it.

---

## 5. Deploy the backend (Fly app #1)

All commands in this step run from the `backend` folder:

```bash
cd backend
```

### 5.1 Pick the app name

Fly app names are **global** across all customers. The default in `backend/fly.toml` is `figsa-api`. Check if it is free:

```bash
fly apps create figsa-api
```

- If it succeeds, continue.
- If it says the name is taken, choose another (e.g. `figsa-api-javi`), create it with that name, and edit the first line of `backend/fly.toml`: `app = "figsa-api-javi"`. **Use your real names everywhere below** (including the URLs `https://figsa-api-javi.fly.dev`).

### 5.2 Set the secrets

Secrets are encrypted environment variables stored by Fly. Replace the placeholders with the values you collected. Keep the quotes.

```bash
fly secrets set --stage -a figsa-api \
  DATABASE_URL="POOLED_URL" \
  MIGRATION_DATABASE_URL="DIRECT_URL" \
  JWT_SECRET="THE_64_CHARACTER_VALUE_FROM_STEP_2" \
  ALLOWED_ORIGINS="https://figsa-web.fly.dev"
```

And, if you did step 3:

```bash
fly secrets set --stage -a figsa-api \
  GOOGLE_CLIENT_ID="..." \
  GOOGLE_CLIENT_SECRET="..." \
  GOOGLE_REFRESH_TOKEN="..."
```

`--stage` saves them without restarting anything; they take effect on the deploy below. `ALLOWED_ORIGINS` must be exactly the address of the website you'll create in step 7 (no trailing slash). If you chose another web app name, use it here.

Check that they are stored (values are never shown):

```bash
fly secrets list -a figsa-api
```

### 5.3 Deploy

```bash
fly deploy
```

What happens: Fly builds the Docker image remotely, then runs `alembic upgrade head` on a temporary machine (this **creates all the tables in Neon**), and only if that succeeds starts the new version. The first deploy takes 2–4 minutes.

Success looks like `✔ Machine ... is now in a good state` and `Visit your newly deployed app at https://figsa-api.fly.dev/`.

### 5.4 Verify

```bash
curl https://figsa-api.fly.dev/healthz
# → {"ok":true}
```

You can also look at the logs: `fly logs -a figsa-api`. And in the Neon console → **Tables** you should see `project`, `activity`, `purchase`, etc.

### 5.5 Create the two users

Only the command line can create users (there is no sign-up page). One user can edit everything (`editor`); the other can only view (`viewer`). Open a shell inside the running backend:

```bash
fly ssh console -a figsa-api
```

Inside that shell run (it asks you to type a password of at least 10 characters; typing is hidden):

```bash
python -m app.cli create-user --email EDITOR_EMAIL --name "Editor name" --role editor
python -m app.cli create-user --email VIEWER_EMAIL --name "Viewer name" --role viewer
python -m app.cli list-users
exit
```

Later you can reset a password with `python -m app.cli set-password --email EMAIL`, from the same kind of shell.

---

## 6. Test the backend before building the website

Check that login works (replace the email and password with the editor's):

```bash
curl -s https://figsa-api.fly.dev/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"EDITOR_EMAIL","password":"THE_PASSWORD"}'
```

You should get JSON containing `access_token`. A wrong password returns `401`.

The API also publishes interactive documentation at `https://figsa-api.fly.dev/docs`.

---

## 7. Deploy the frontend (Fly app #2)

### 7.1 Create the app and point it at the API

```bash
cd ../frontend
fly apps create figsa-web
```

(Same rule as before: if the name is taken, choose another and set it in `frontend/fly.toml` → `app = "..."`.)

Open `frontend/fly.toml` and check the build argument matches your **API** address, ending in `/api/v1`:

```toml
[build.args]
  VITE_API_URL = "https://figsa-api.fly.dev/api/v1"
```

> This value is baked into the website when it is built. If you ever rename the API, change this line and redeploy the frontend.

### 7.2 Deploy

```bash
fly deploy
```

The build installs npm packages and compiles the React app (1–3 minutes), then serves it with nginx.

### 7.3 Allow the website to talk to the API (CORS)

If your web app is **not** named `figsa-web`, update the backend setting now (otherwise the browser blocks every request). It is safe to run this even if the name is the same:

```bash
fly secrets set -a figsa-api ALLOWED_ORIGINS="https://figsa-web.fly.dev"
```

This restarts the API (a few seconds).

### 7.4 Open it

Go to **https://figsa-web.fly.dev**, sign in with the editor account. You should see an empty **Portafolio**.

---

## 8. First-use checklist

Do these in the app, signed in as the editor:

1. **Portafolio → + Proyecto**: create your first project (code such as `CEM`, name, priority). Paste the Drive folder URLs (step 3.1) into *Carpeta de Drive · facturas / comprobantes*. Set the *Inicio del escenario* date, used to project activities without dates.
2. **Actividades → + Actividad**: add activities with their dependencies ("Depende de" = codes separated by commas).
3. **Rendimiento financiero → + Línea**: add budget lines; then in **Compras y pagos** create purchases and tag them with a budget line.
4. **Compras y pagos** → open a purchase → *Subir a Drive* on the Factura slot. The file should appear in the Drive folder.
5. Sign out, sign in as the viewer: every create/edit button is hidden and every form is read-only. (The server also rejects any write from this user.)

---

## 9. Everyday operations

### Deploy a new version
After changing code:

```bash
git add -A && git commit -m "Describe the change" && git push
cd backend  && fly deploy     # runs migrations automatically
cd ../frontend && fly deploy
```

### Database changes (migrations)
Add a new file in `backend/alembic/versions/` (copy the style of `0001_initial.py`, set `down_revision` to the previous revision). `fly deploy` applies it. If the migration fails, the release is cancelled and the old version keeps running; read why with `fly logs -a figsa-api`.

### See logs and status
```bash
fly status -a figsa-api
fly logs   -a figsa-api
fly logs   -a figsa-web
```

### Change a secret
```bash
fly secrets set -a figsa-api JWT_SECRET="NEW_VALUE"     # restarts the API; everybody must log in again
```

### Backups
Neon keeps a history of your database that lets you restore to an earlier moment; how far back depends on your Neon plan (see the **Backup & restore** section in the Neon console). For an extra copy you can control, run on your Mac (needs `brew install libpq`):

```bash
pg_dump "DIRECT_URL" --no-owner -Fc -f figsa-$(date +%F).dump
```

### Custom domain (optional)
```bash
fly certs add app.yourdomain.com -a figsa-web
```
Fly prints the DNS records to create at your domain provider. After it works, update `ALLOWED_ORIGINS` on the API to the new address (you can list several separated by commas) and, if you also give the API a domain, `VITE_API_URL` in `frontend/fly.toml`, then redeploy both.

### Delete everything
```bash
fly apps destroy figsa-web
fly apps destroy figsa-api
```
and delete the project in the Neon console. Drive files stay in your Drive.

---

## 10. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `fly apps create` says the name is taken | Choose another name; update `app =` in that folder's `fly.toml`, and use it in every URL and in `ALLOWED_ORIGINS` / `VITE_API_URL`. |
| `fly deploy` (backend) fails at **release command** | Migrations could not run. Read `fly logs -a figsa-api`. Usual cause: wrong `MIGRATION_DATABASE_URL`. It must be the **direct** string (no `-pooler`) and include `?sslmode=require`. Fix with `fly secrets set`, then deploy again. |
| Login page shows "No se pudo conectar con el servidor" | The website cannot reach the API: check `VITE_API_URL` in `frontend/fly.toml` (must end in `/api/v1` and be your real API address), then redeploy the frontend. Test `curl https://figsa-api.fly.dev/healthz`. |
| Browser console shows a **CORS** error | `ALLOWED_ORIGINS` on the API does not exactly equal the website's address (scheme included, no trailing slash). Fix it as in step 7.3. |
| "Correo o contraseña incorrectos" for a user you just created | Check you typed the exact email (case does not matter) and that `list-users` shows it. Reset with `set-password`. |
| Everything is slow on the first request of the day | Neon wakes up from sleep (free plan) and/or the web machine starts. Later requests are fast. |
| `/healthz` works but pages show server errors | `fly logs -a figsa-api` — a Python traceback tells you the cause. Frequent one: `DATABASE_URL` missing `?sslmode=require`. |
| Uploading a file says "carpeta de Drive" | The project has no Drive folder URL yet. Open the project and fill the folder fields. |
| Upload says Drive is not configured | The three `GOOGLE_*` secrets are missing (step 3 + step 5.2). |
| Upload says the folder was not found / no access | The folder belongs to a different Google account than the one you authorised, or the URL is wrong. Open the folder in the same Google account or re-run step 3.6 with the right account. |
| Uploads worked, then stopped about a week later | The OAuth app was left in **Testing**. Publish it to **Production** (step 3.4) and re-run step 3.6 to get a new token. |
| `fly ssh console` says no machines | Run `fly machine list -a figsa-api` and start one with `fly machine start MACHINE_ID -a figsa-api`. |
| Changed the frontend but see the old page | Hard refresh (Cmd+Shift+R). The page itself is never cached, only hashed assets are. |
| "Alguien más modificó este registro" when saving | Someone else saved the same record after you opened it. Close the form, reopen it, and re-apply your change. |

---

## 11. Reference

### Backend environment variables

| Variable | Required | Meaning |
|---|---|---|
| `DATABASE_URL` | yes | Neon **pooled** connection string. |
| `MIGRATION_DATABASE_URL` | recommended | Neon **direct** string, used only by `alembic upgrade head`. Falls back to `DATABASE_URL`. |
| `JWT_SECRET` | yes | Long random string that signs logins (`openssl rand -hex 32`). |
| `ALLOWED_ORIGINS` | yes | Website address(es) allowed to call the API, comma separated. |
| `TZ` | no | Defaults to `America/Guatemala`; "today" for all date logic is computed in this zone. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` | for Drive | From step 3. |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | alternative | Only if you use a Google Workspace *Shared Drive* with a service account instead of the three values above. |

### Frontend build variable

| Variable | Meaning |
|---|---|
| `VITE_API_URL` | Public API address ending in `/api/v1`. Set in `frontend/fly.toml` → `[build.args]`. |

### Roles

| Role | Can do |
|---|---|
| `editor` | Create, edit and delete everything; upload files; complete tasks. |
| `viewer` | Read everything. Every write is rejected by the server (HTTP 403). |
