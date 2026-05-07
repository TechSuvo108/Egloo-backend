from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://egloo:egloo@localhost:5432/egloo"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change-this-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Encryption (for OAuth tokens stored in DB)
    ENCRYPTION_KEY: str = "change-this-encryption-key-in-production"

    # LLM API Keys
    GEMINI_API_KEYS: Optional[str] = None
    GROQ_API_KEYS: Optional[str] = None
    OPENROUTER_API_KEYS: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GEMINI_MODEL: str = "gemini-1.5-flash-latest"

    # LLM timeouts (seconds)
    GEMINI_TIMEOUT: int = 30
    GROQ_TIMEOUT: int = 20
    OPENROUTER_TIMEOUT: int = 45

    # Retry settings
    LLM_MAX_RETRIES: int = 2
    LLM_RETRY_DELAY: float = 1.0

    # Provider health TTL
    LLM_HEALTH_TTL: int = 120

    # How many chunks to retrieve from ChromaDB per query
    RAG_TOP_K: int = 8

    # Redis TTL for cached query answers (1 hour)
    QUERY_CACHE_TTL: int = 3600

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/sources/callback/gmail"

    # Slack OAuth
    SLACK_CLIENT_ID: Optional[str] = None
    SLACK_CLIENT_SECRET: Optional[str] = None
    SLACK_REDIRECT_URI: str = "http://localhost:8000/api/v1/sources/callback/slack"

    # ChromaDB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001

    # Digest settings
    DIGEST_LOOKBACK_HOURS: int = 24
    DIGEST_MAX_CHUNKS: int = 200
    DIGEST_MIN_CHUNKS: int = 3

    # FCM (Firebase Cloud Messaging) — optional
    # Download your Firebase service account JSON from Firebase Console
    # and put the path here. Leave empty to disable push notifications.
    FCM_CREDENTIALS_PATH: Optional[str] = None

    # App timezone for digest scheduling
    APP_TIMEZONE: str = "UTC"

    # Feature Flag: Use Celery for ingestion (Default False for cloud free-tier)
    USE_ASYNC_INGEST: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
