import asyncio
import redis.asyncio as aioredis
from app.config import settings

# We store the client in a way that allows us to manage its lifecycle.
# In a FastAPI context, we want a singleton. 
# In a Celery context (with asyncio.run), we need it to be loop-aware or recreated.

_redis_client = None

def get_redis_client():
    """
    Returns the global Redis client.
    Note: In Celery tasks using asyncio.run(), the client should be 
    used carefully to avoid loop mismatch.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL, 
            decode_responses=True,
            encoding="utf-8",
            # We don't initialize the pool until first use
        )
    return _redis_client

async def close_redis_client():
    """
    Closes the Redis client connections.
    Crucial for Celery tasks to avoid 'Event loop is closed' errors.
    """
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None

async def check_redis_health():
    """Simple ping to verify connectivity."""
    client = get_redis_client()
    try:
        return await client.ping()
    except Exception:
        return False
