"""
Sources router — OAuth connect / disconnect / status endpoints.

Prefix: /api/v1
Tag:    sources

Endpoints
---------
GET  /sources                         – list all connected sources for the current user
GET  /sources/connect/gmail           – initiate Google (Gmail + Drive) OAuth flow
GET  /sources/connect/slack           – initiate Slack OAuth flow
GET  /sources/callback/gmail          – Google OAuth callback handler
GET  /sources/callback/slack          – Slack OAuth callback handler
DELETE /sources/{source_type}         – disconnect (delete) a source
GET  /sources/{source_type}/status    – get sync status for a specific source
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.source import MessageResponse, SourceListResponse, SourceResponse, SyncStatusResponse
from app.services import google_oauth, slack_oauth, source_service
from app.utils.oauth_state import generate_state, verify_and_consume_state

router = APIRouter(tags=["sources"])


# ---------------------------------------------------------------------------
# List sources
# ---------------------------------------------------------------------------

@router.get(
    "/sources",
    response_model=SourceListResponse,
    summary="List all connected data sources",
)
async def list_sources(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return every data source connected to the authenticated user's account."""
    sources = await source_service.get_all_sources(db, current_user.id)
    return SourceListResponse(
        sources=[SourceResponse.model_validate(s) for s in sources],
        total=len(sources),
    )


# ---------------------------------------------------------------------------
# Connect — initiate OAuth
# ---------------------------------------------------------------------------

@router.get(
    "/sources/connect/gmail",
    summary="Initiate Google (Gmail + Drive) OAuth flow",
    response_class=RedirectResponse,
)
async def connect_gmail(
    current_user: User = Depends(get_current_user),
):
    """Generate a CSRF state token and redirect the user to Google's consent screen."""
    state = await generate_state(str(current_user.id))
    url = google_oauth.build_google_auth_url(state=state)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.get(
    "/sources/connect/slack",
    summary="Initiate Slack OAuth flow",
    response_class=RedirectResponse,
)
async def connect_slack(
    current_user: User = Depends(get_current_user),
):
    """Generate a CSRF state token and redirect the user to Slack's consent screen."""
    state = await generate_state(str(current_user.id))
    url = slack_oauth.build_slack_auth_url(state=state)
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


# ---------------------------------------------------------------------------
# Callbacks — handle OAuth redirect
# ---------------------------------------------------------------------------

@router.get(
    "/sources/callback/gmail",
    summary="Google OAuth callback — store tokens and redirect",
)
async def gmail_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="CSRF state token"),
    error: str | None = Query(None, description="Error code from Google, if any"),
    db: AsyncSession = Depends(get_db),
):
    """Handle Google's redirect after the user grants (or denies) consent.

    On success: exchanges the auth code for tokens, stores them encrypted,
    and returns a success JSON response.  In a production frontend you would
    instead redirect to a deep-link / frontend URL.
    """
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth denied: {error}",
        )

    # We need the user_id from the state to verify ownership.
    # Peek without consuming so we can get the user_id first.
    from app.utils import oauth_state as _os
    import redis.asyncio as aioredis
    from app.config import settings as _settings

    _redis = aioredis.from_url(_settings.REDIS_URL, decode_responses=True)
    stored_user_id = await _redis.get(f"oauth_state:{state}")

    if stored_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state. Please try connecting again.",
        )

    valid = await verify_and_consume_state(state, stored_user_id)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state mismatch. Possible CSRF attempt.",
        )

    try:
        token_data = await google_oauth.exchange_google_code(code)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to exchange Google auth code: {exc}",
        )

    from uuid import UUID

    await source_service.upsert_source(
        db=db,
        user_id=UUID(stored_user_id),
        source_type="gmail",
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_expiry=token_data.get("expires_at"),
        source_metadata={"scope": token_data.get("scope", "")},
    )

    return {"message": "Gmail connected successfully.", "source_type": "gmail"}


@router.get(
    "/sources/callback/slack",
    summary="Slack OAuth callback — store tokens and redirect",
)
async def slack_callback(
    code: str = Query(..., description="Authorization code from Slack"),
    state: str = Query(..., description="CSRF state token"),
    error: str | None = Query(None, description="Error code from Slack, if any"),
    db: AsyncSession = Depends(get_db),
):
    """Handle Slack's redirect after the user grants (or denies) consent."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Slack OAuth denied: {error}",
        )

    import redis.asyncio as aioredis
    from app.config import settings as _settings

    _redis = aioredis.from_url(_settings.REDIS_URL, decode_responses=True)
    stored_user_id = await _redis.get(f"oauth_state:{state}")

    if stored_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state. Please try connecting again.",
        )

    valid = await verify_and_consume_state(state, stored_user_id)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state mismatch. Possible CSRF attempt.",
        )

    try:
        token_data = await slack_oauth.exchange_slack_code(code)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to exchange Slack auth code: {exc}",
        )

    from uuid import UUID

    team: dict = token_data.get("team", {})
    authed_user: dict = token_data.get("authed_user", {})

    await source_service.upsert_source(
        db=db,
        user_id=UUID(stored_user_id),
        source_type="slack",
        access_token=token_data["user_access_token"],
        refresh_token=None,  # Slack user tokens don't expire / use refresh
        token_expiry=token_data.get("expires_at"),
        source_metadata={
            "team_id": team.get("id", ""),
            "team_name": team.get("name", ""),
            "slack_user_id": authed_user.get("id", ""),
        },
    )

    return {"message": "Slack connected successfully.", "source_type": "slack"}


# ---------------------------------------------------------------------------
# Disconnect
# ---------------------------------------------------------------------------

@router.delete(
    "/sources/{source_type}",
    response_model=MessageResponse,
    summary="Disconnect a data source",
)
async def disconnect_source(
    source_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove the stored OAuth tokens for the given *source_type*.

    Valid values: ``gmail``, ``slack``, ``google_drive``.
    """
    _VALID = {"gmail", "slack", "google_drive"}
    if source_type not in _VALID:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown source type '{source_type}'. Must be one of {_VALID}.",
        )

    deleted = await source_service.delete_source(db, current_user.id, source_type)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No connected source of type '{source_type}' found.",
        )

    return MessageResponse(message=f"{source_type} disconnected successfully.")


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.get(
    "/sources/{source_type}/status",
    response_model=SyncStatusResponse,
    summary="Get sync status for a specific source",
)
async def get_source_status(
    source_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current sync status for the requested *source_type*."""
    source = await source_service.get_source_by_type(db, current_user.id, source_type)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_type}' is not connected.",
        )

    return SyncStatusResponse(
        source_id=source.id,
        source_type=source.source_type,
        sync_status=source.sync_status,
        last_synced_at=source.last_synced_at,
        message=f"Source '{source_type}' is {source.sync_status}.",
    )
