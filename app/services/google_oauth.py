"""
Google OAuth 2.0 service — Gmail & Google Drive.

Handles:
  • Building the authorization URL (with PKCE-less code flow)
  • Exchanging the authorization code for tokens
  • Refreshing an expired access token
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.config import settings

# Google OAuth endpoints
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Scopes requested for Gmail + Google Drive read access
_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def build_google_auth_url(state: str, redirect_uri: Optional[str] = None) -> str:
    """Return the Google consent-screen URL to redirect the user to.

    Args:
        state: An opaque CSRF token previously stored in Redis via
               ``oauth_state.generate_state()``.
        redirect_uri: Optional override for the redirect URI. 
                      Defaults to settings.GOOGLE_REDIRECT_URI.
    """
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri or settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(_SCOPES),
        "access_type": "offline",   # request a refresh_token
        "prompt": "consent",        # force refresh_token even on re-auth
        "state": state,
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_google_code(code: str, redirect_uri: Optional[str] = None) -> dict:
    """Exchange an authorization *code* for access + refresh tokens.

    Returns the raw token JSON from Google which includes at minimum:
        access_token, expires_in, token_type, scope
    and (on first consent) refresh_token.

    Raises:
        httpx.HTTPStatusError – if Google returns a non-2xx response.
        ValueError             – if the response is missing access_token.
    """
    payload = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri or settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(_TOKEN_URL, data=payload, timeout=15)
        resp.raise_for_status()

    data = resp.json()

    if "access_token" not in data:
        raise ValueError(f"Google token exchange failed: {data}")

    # Compute absolute expiry timestamp
    expires_in: int = data.get("expires_in", 3600)
    data["expires_at"] = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    return data


async def refresh_google_access_token(refresh_token: str) -> dict:
    """Use a stored *refresh_token* to obtain a fresh access token.

    Returns the token JSON (same shape as ``exchange_google_code`` response,
    minus refresh_token which Google does not re-issue on refresh).

    Raises:
        httpx.HTTPStatusError – on HTTP error.
        ValueError             – if access_token is absent in response.
    """
    payload = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(_TOKEN_URL, data=payload, timeout=15)
        resp.raise_for_status()

    data = resp.json()

    if "access_token" not in data:
        raise ValueError(f"Google token refresh failed: {data}")

    expires_in: int = data.get("expires_in", 3600)
    data["expires_at"] = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    return data


async def fetch_user_info(access_token: str) -> dict:
    """Fetch user profile info (email, name) using the access token.

    Used to populate source metadata (account_name, email).
    """
    url = "https://www.googleapis.com/oauth2/v3/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
    return resp.json()
