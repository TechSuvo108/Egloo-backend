from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from app.config import settings

async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=True,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db():
    """Dependency that yields an async DB session and closes it afterwards."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def dispose_engine():
    """Explicitly dispose of the engine and its connection pool."""
    await async_engine.dispose()
