"""
Slack OAuth 2.0 service (v2 flow — Bot + User token).

Handles:
  • Building the Slack OAuth authorization URL
  • Exchanging the authorization code for user + bot tokens
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings

# Slack OAuth v2 endpoints
_AUTH_URL = "https://slack.com/oauth/v2/authorize"
_TOKEN_URL = "https://slack.com/api/oauth.v2.access"

# User scopes required to read messages and channels
_USER_SCOPES = [
    "channels:history",
    "channels:read",
    "groups:history",
    "groups:read",
    "im:history",
    "im:read",
    "mpim:history",
    "mpim:read",
    "users:read",
    "users:read.email",
]

# Bot scopes (basic bot presence)
_BOT_SCOPES: list[str] = []


def build_slack_auth_url(state: str) -> str:
    """Return the Slack consent-screen URL to redirect the user to.

    Args:
        state: An opaque CSRF token previously stored in Redis via
               ``oauth_state.generate_state()``.
    """
    params = {
        "client_id": settings.SLACK_CLIENT_ID,
        "redirect_uri": settings.SLACK_REDIRECT_URI,
        "user_scope": ",".join(_USER_SCOPES),
        "state": state,
    }

    if _BOT_SCOPES:
        params["scope"] = ",".join(_BOT_SCOPES)

    return f"{_AUTH_URL}?{urlencode(params)}"


async def exchange_slack_code(code: str) -> dict:
    """Exchange a Slack authorization *code* for access tokens.

    Returns the raw Slack API response which includes (among others):
        ok, access_token (bot), authed_user.access_token (user token),
        team.id, team.name, authed_user.id.

    Raises:
        httpx.HTTPStatusError – on HTTP error.
        ValueError             – if ``ok`` is False or user token is absent.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.SLACK_CLIENT_ID,
                "client_secret": settings.SLACK_CLIENT_SECRET,
                "redirect_uri": settings.SLACK_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        resp.raise_for_status()

    data = resp.json()

    if not data.get("ok"):
        raise ValueError(f"Slack token exchange failed: {data.get('error', 'unknown')}")

    # Normalise: surface the user-level access token at the top level for
    # consistency with the Google flow and source_service expectations.
    authed_user: dict = data.get("authed_user", {})
    user_token: str = authed_user.get("access_token", "")

    if not user_token:
        raise ValueError("Slack did not return a user-level access token.")

    # Slack user tokens do not expire (no expires_in), so we store a far-future
    # expiry to keep the DB column consistent.
    data["user_access_token"] = user_token
    data["expires_at"] = datetime.now(timezone.utc) + timedelta(days=365 * 10)

    return data
