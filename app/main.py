from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.routers import (
    auth, sources, ingest,
    query, llm, digest,
    topics, saved, brain,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    print("\n🐧 Egloo API starting — Pingo is hatching...")

    # Validate environment
    from app.utils.env_validator import print_env_report
    is_valid = print_env_report()

    # Check Redis
    try:
        from app.utils.redis_client import check_redis_health
        if await check_redis_health():
            print("✅ Redis connected")
        else:
            print("⚠️  Redis not reachable (limited functionality)")
    except Exception as e:
        print(f"❌ Redis check error: {e}")

    # Check ChromaDB
    try:
        from app.utils.chroma_client import get_chroma_client
        client = get_chroma_client()
        client.heartbeat()
        print("✅ ChromaDB connected")
    except Exception as e:
        print(f"⚠️  ChromaDB not available: {e}")

    print("🐧 Pingo is ready!\n")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    print("🐧 Egloo API shutting down — Pingo is sleeping...")


# ── Create app ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Egloo API — Pingo Second Brain",
    version="1.0.0",
    description="""
## 🐧 Egloo — Your Second Brain, Powered by Pingo

Egloo connects your Gmail, Slack, and Google Drive into a single
intelligent assistant. Ask questions, get daily digests, and never
miss an action item again.

### Core Features
- **Auth** — JWT-based register, login, logout with Redis blacklist
- **Sources** — Connect Gmail, Slack, Google Drive via OAuth 2.0
- **Ingest** — Fetch, chunk, embed, and store your data in ChromaDB
- **Query** — Ask Pingo anything about your data (RAG pipeline)
- **Digest** — Auto-generated daily summaries with action items
- **Topics** — Auto-clustered topic groups from your data
- **Saved** — Bookmark digests and query results

### LLM Fallback Chain
Gemini → Groq → OpenRouter (automatic failover)

### Getting Started
1. `POST /api/v1/auth/register` — create account
2. `GET /api/v1/sources/connect/gmail` — connect Gmail
3. `POST /api/v1/ingest/trigger-direct/{source_id}` — ingest data
4. `POST /api/v1/query/ask` — ask Pingo a question
5. `GET /api/v1/digest/today` — view daily digest
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(auth.router,    prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")
app.include_router(ingest.router,  prefix="/api/v1")
app.include_router(query.router,   prefix="/api/v1")
app.include_router(llm.router,     prefix="/api/v1")
app.include_router(digest.router,  prefix="/api/v1")
app.include_router(topics.router,  prefix="/api/v1")
app.include_router(saved.router,   prefix="/api/v1")
app.include_router(brain.router,   prefix="/api/v1/brain")


# ── Root endpoints ────────────────────────────────────────────────────────────

@app.get("/", tags=["🐧 Root"])
async def root():
    return {
        "app": "Egloo",
        "assistant": "Pingo",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["🐧 Root"])
async def health():
    """
    Real health check — tests actual connections to
    PostgreSQL, Redis, and ChromaDB.
    Returns 200 if all critical services are up.
    Returns 503 if any critical service is down.
    """
    results = {}
    all_ok = True

    # Check PostgreSQL
    try:
        from app.database import async_engine
        from sqlalchemy import text
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        results["postgres"] = "connected"
    except Exception as e:
        results["postgres"] = f"error: {str(e)[:60]}"
        all_ok = False

    # Check Redis
    try:
        import redis.asyncio as aioredis
        from app.config import settings
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        results["redis"] = "connected"
    except Exception as e:
        results["redis"] = f"error: {str(e)[:60]}"
        all_ok = False

    # Check ChromaDB
    try:
        from app.utils.chroma_client import get_chroma_client
        get_chroma_client().heartbeat()
        results["chroma"] = "connected"
    except Exception as e:
        results["chroma"] = f"unavailable: {str(e)[:60]}"
        # ChromaDB is not critical for auth/query cache to work
        # so we warn but don't fail

    # Check LLM
    try:
        from app.config import settings
        llm_keys = {
            "gemini": bool(settings.GEMINI_API_KEYS),
            "groq": bool(settings.GROQ_API_KEYS),
            "openrouter": bool(settings.OPENROUTER_API_KEYS),
        }
        configured = [k for k, v in llm_keys.items() if v]
        results["llm"] = (
            f"configured: {', '.join(configured)}"
            if configured
            else "no providers configured"
        )
    except Exception as e:
        results["llm"] = f"error: {str(e)[:60]}"

    status_code = 200 if all_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if all_ok else "degraded",
            "services": results,
            "assistant": "Pingo 🐧",
        },
    )
