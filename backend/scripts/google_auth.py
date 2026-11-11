"""One-time helper: get the Google Drive refresh token the backend needs.

Run it on YOUR computer (it opens a browser):

    cd backend
    python -m venv .venv && source .venv/bin/activate
    pip install google-auth-oauthlib
    python scripts/google_auth.py --client-id XXX.apps.googleusercontent.com --client-secret YYY

Sign in with the Google account that OWNS the Drive folders, accept the permissions, and copy the
three values it prints into Fly secrets (see deployment.md).
"""
import argparse

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]

ap = argparse.ArgumentParser()
ap.add_argument("--client-id", required=True)
ap.add_argument("--client-secret", required=True)
a = ap.parse_args()

flow = InstalledAppFlow.from_client_config(
    {"installed": {
        "client_id": a.client_id, "client_secret": a.client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }},
    SCOPES,
)
# access_type=offline + prompt=consent forces Google to return a refresh token every time.
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
if not creds.refresh_token:
    raise SystemExit("Google did not return a refresh token. Remove the app at https://myaccount.google.com/permissions and run again.")
print("\n=== Copy these into Fly secrets ===")
print(f"GOOGLE_CLIENT_ID={a.client_id}")
print(f"GOOGLE_CLIENT_SECRET={a.client_secret}")
print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
