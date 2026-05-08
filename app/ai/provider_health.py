from app.utils.redis_client import get_redis_client
from app.config import settings


def get_redis():
    """Fallback to centralized client."""
    return get_redis_client()


async def mark_unhealthy(provider: str, reason: str):
    """
    Mark a provider as unhealthy in Redis.
    It will be skipped for LLM_HEALTH_TTL seconds.
    """
    key = f"llm_health:{provider}"
    redis_client = get_redis()
    try:
        await redis_client.setex(
            key,
            settings.LLM_HEALTH_TTL,
            reason,
        )
    except Exception as e:
        print(f"[WARNING] Redis error: {e}")
    print(f"[WARNING] Provider {provider} marked unhealthy: {reason}")


async def mark_healthy(provider: str):
    """
    Mark a provider as healthy — removes unhealthy flag.
    Called after a successful response.
    """
    key = f"llm_health:{provider}"
    redis_client = get_redis()
    try:
        await redis_client.delete(key)
    except Exception as e:
        print(f"[WARNING] Redis error: {e}")


async def is_healthy(provider: str) -> bool:
    """
    Returns True if provider is healthy (no flag in Redis).
    Returns False if provider is marked unhealthy.
    """
    key = f"llm_health:{provider}"
    redis_client = get_redis()
    try:
        result = await redis_client.get(key)
        return result is None
    except Exception as e:
        print(f"[WARNING] Redis error: {e}")
        return True


async def get_all_health() -> dict:
    """
    Returns health status of all 3 providers.
    Used by the /llm/health endpoint.
    """
    providers = ["gemini", "groq", "openrouter"]
    health = {}
    redis_client = get_redis()
    for provider in providers:
        key = f"llm_health:{provider}"
        try:
            reason = await redis_client.get(key)
            health[provider] = {
                "healthy": reason is None,
                "reason": reason or "ok",
            }
        except Exception as e:
            print(f"[WARNING] Redis error: {e}")
            health[provider] = {
                "healthy": True,
                "reason": "ok",
            }
    return health


async def log_usage(provider: str, success: bool, tokens_est: int = 0):
    """
    Increment usage counters in Redis.
    Used to track which provider is being used most.
    Counters never expire — use for monitoring.
    """
    status = "success" if success else "failure"
    redis_client = get_redis()
    try:
        await redis_client.incr(f"llm_usage:{provider}:{status}")
        if tokens_est > 0:
            await redis_client.incrby(f"llm_tokens:{provider}", tokens_est)
    except Exception as e:
        print(f"[WARNING] Redis error: {e}")


async def get_usage_stats() -> dict:
    """Returns usage stats for all providers."""
    providers = ["gemini", "groq", "openrouter"]
    stats = {}
    redis_client = get_redis()
    for provider in providers:
        try:
            success = await redis_client.get(f"llm_usage:{provider}:success") or "0"
            failure = await redis_client.get(f"llm_usage:{provider}:failure") or "0"
            tokens = await redis_client.get(f"llm_tokens:{provider}") or "0"
            stats[provider] = {
                "success_calls": int(success),
                "failure_calls": int(failure),
                "estimated_tokens": int(tokens),
            }
        except Exception as e:
            print(f"[WARNING] Redis error: {e}")
            stats[provider] = {
                "success_calls": 0,
                "failure_calls": 0,
                "estimated_tokens": 0,
            }
    return stats
