from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, sources
from app.services.auth_service import check_redis_connection


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[STARTUP] Egloo API starting... PenGo is waking up!")
    await check_redis_connection()
    print("[OK] Redis connected")
    yield
    print("[SHUTDOWN] Egloo API shutting down... PenGo is sleeping!")


app = FastAPI(
    title="Egloo API",
    version="1.0.0",
    description="PenGo — Your second brain assistant 🐧",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(sources.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "message": "Welcome to Egloo",
        "status": "running",
        "assistant": "PenGo",
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "database": "connected",
        "redis": "connected",
    }
