"""
YouTube Data API v3 uploader with OAuth 2.0.

Setup required:
  1. Create a project at https://console.cloud.google.com/
  2. Enable "YouTube Data API v3"
  3. Create OAuth 2.0 credentials (Desktop App)
  4. Download and save as  backend/client_secrets.json

Authentication flow:
  - GET  /api/youtube/auth      → returns {auth_url}
  - GET  /api/youtube/callback  → exchanges code, stores yt_token.json
  - POST /api/youtube/upload    → uploads the clip as private short
"""

import json
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
SECRETS_FILE = BACKEND_DIR / "client_secrets.json"
TOKEN_FILE = BACKEND_DIR / "yt_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def secrets_available() -> bool:
    return SECRETS_FILE.exists()


def get_auth_url(redirect_uri: str) -> str:
    if not secrets_available():
        raise RuntimeError(
            "client_secrets.json not found. "
            "Download it from Google Cloud Console and place it in the backend/ folder."
        )
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(
        str(SECRETS_FILE), scopes=SCOPES, redirect_uri=redirect_uri
    )
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return auth_url


def exchange_code(code: str, redirect_uri: str) -> None:
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(
        str(SECRETS_FILE), scopes=SCOPES, redirect_uri=redirect_uri
    )
    flow.fetch_token(code=code)
    creds = flow.credentials
    TOKEN_FILE.write_text(
        json.dumps(
            {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes or SCOPES),
            }
        )
    )


def get_saved_credentials():
    if not TOKEN_FILE.exists():
        return None
    from google.oauth2.credentials import Credentials
    data = json.loads(TOKEN_FILE.read_text())
    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes", SCOPES),
    )


def upload_short(file_path: str, title: str, description: str = "#Shorts") -> str:
    """Upload file_path to YouTube as a private Short, return its URL."""
    creds = get_saved_credentials()
    if creds is None:
        raise RuntimeError(
            "Not authenticated. Open /api/youtube/auth in your browser first."
        )
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": ["shorts", "ai", "generated"],
            "categoryId": "22",
        },
        "status": {"privacyStatus": "private"},
    }
    media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)
    response = (
        youtube.videos()
        .insert(part="snippet,status", body=body, media_body=media)
        .execute()
    )
    return f"https://youtu.be/{response['id']}"
