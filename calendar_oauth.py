import os
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar"
]

# ✅ MUST come from environment variable (Render / local)
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")


def get_oauth_flow():
    if not REDIRECT_URI:
        raise RuntimeError("GOOGLE_REDIRECT_URI is not set")

    return Flow.from_client_config(
        {
            "web": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI],
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )


def build_calendar_service(credentials):
    return build("calendar", "v3", credentials=credentials)
