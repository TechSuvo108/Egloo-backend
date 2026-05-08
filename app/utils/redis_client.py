import asyncio
import redis.asyncio as aioredis
from app.config import settings

# We store the client in a way that allows us to manage its lifecycle.
# In a FastAPI context, we want a singleton. 
# In a Celery context (with asyncio.run), we need it to be loop-aware or recreated.

_redis_client = None
_loop = None

def get_redis_client():
    """
    Returns a loop-aware Redis client.
    Recreates the client if the event loop has changed (e.g. in tests).
    """
    global _redis_client, _loop
    
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _redis_client is None or _loop != current_loop:
        # Recreate client for the new loop
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            encoding="utf-8",
        )
        _loop = current_loop
        
    return _redis_client

async def close_redis():
    """
    Closes the Redis client connections cleanly.
    """
    global _redis_client, _loop
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None
        _loop = None

async def check_redis_health():
    """Simple ping to verify connectivity."""
    try:
        client = get_redis_client()
        return await client.ping()
    except Exception:
        return False
