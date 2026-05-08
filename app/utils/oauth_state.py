"""
Stateless OAuth state parameter helpers backed by Redis.

Flow:
  1. Before redirecting the user to Google / Slack, call `generate_state()`.
     The returned opaque token is appended to the OAuth redirect URL as ?state=…
  2. In the callback handler, call `verify_and_consume_state(state, user_id)`.
     Returns True only if the state was issued for that user and has not expired.

States are stored in Redis with a short TTL (default 10 minutes) to prevent
CSRF.  They are single-use — verified states are deleted immediately.
"""

import secrets
from app.utils.redis_client import get_redis_client

def get_redis():
    """Returns a loop-safe Redis client."""
    return get_redis_client()

_STATE_TTL_SECONDS = 600  # 10 minutes
_KEY_PREFIX = "oauth_state:"


def _state_key(state: str) -> str:
    return f"{_KEY_PREFIX}{state}"


async def generate_state(user_id: str) -> str:
    """Generate a cryptographically random state token tied to *user_id*.

    Stores ``user_id`` in Redis under the state key with a 10-minute TTL and
    returns the opaque state token to embed in the OAuth redirect URL.
    """
    state = secrets.token_urlsafe(32)
    await get_redis().setex(_state_key(state), _STATE_TTL_SECONDS, user_id)
    return state


async def verify_and_consume_state(state: str, user_id: str) -> bool:
    """Verify that *state* was issued for *user_id* and delete it atomically.

    Returns:
        True  – state is valid for this user (caller may proceed with OAuth).
        False – state is missing, expired, or belongs to a different user.
    """
    key = _state_key(state)
    stored_user_id = await get_redis().get(key)

    if stored_user_id is None:
        return False  # expired or never existed

    if stored_user_id != str(user_id):
        return False  # CSRF: state doesn't belong to this user

    # Single-use: delete immediately after verification
    await get_redis().delete(key)
    return True
