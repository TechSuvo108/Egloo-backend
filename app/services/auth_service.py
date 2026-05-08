from datetime import datetime, timedelta, timezone
from uuid import UUID
from typing import Optional, Tuple

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.config import settings

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


from app.utils.redis_client import get_redis_client

def get_redis():
    """Returns a loop-safe Redis client."""
    return get_redis_client()




# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def create_access_token(user_id: UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ---------------------------------------------------------------------------
# Redis token helpers
# ---------------------------------------------------------------------------
async def save_refresh_token(user_id: UUID, refresh_token: str):
    key = f"refresh_token:{str(user_id)}"
    ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    await get_redis().setex(key, ttl, refresh_token)


async def blacklist_access_token(token: str, expires_in_seconds: int):
    key = f"blacklist:{token}"
    await get_redis().setex(key, expires_in_seconds, "blacklisted")


async def is_token_blacklisted(token: str) -> bool:
    key = f"blacklist:{token}"
    result = await get_redis().get(key)
    return result is not None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Business logic
# ---------------------------------------------------------------------------
async def register_user(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: Optional[str],
) -> Tuple[str, str, User]:
    """
    Registers a new user and returns (access_token, refresh_token, user).
    Raises ValueError on duplicate email or DB error.
    """
    existing = await get_user_by_email(db, email)
    if existing:
        raise ValueError("Email already registered")

    hashed = hash_password(password)
    user = User(email=email, hashed_password=hashed, full_name=full_name)
    db.add(user)

    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise ValueError("Email already registered")

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    await save_refresh_token(user.id, refresh_token)

    return access_token, refresh_token, user


async def login_user(
    db: AsyncSession,
    email: str,
    password: str,
) -> Tuple[str, str, User]:
    user = await get_user_by_email(db, email)
    if not user or not verify_password(password, user.hashed_password):
        raise ValueError("Invalid email or password")
    if not user.is_active:
        raise ValueError("Account is deactivated")

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    await save_refresh_token(user.id, refresh_token)

    return access_token, refresh_token, user


async def refresh_access_token(
    refresh_token: str,
    db: AsyncSession,
) -> Tuple[str, str]:
    try:
        payload = jwt.decode(
            refresh_token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")
        user_id: str = payload.get("sub")
    except JWTError:
        raise ValueError("Invalid or expired refresh token")

    stored = await get_redis().get(f"refresh_token:{user_id}")
    if stored != refresh_token:
        raise ValueError("Refresh token has been rotated or invalidated")

    user = await get_user_by_id(db, user_id)
    if not user:
        raise ValueError("User not found")

    new_access = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)
    await save_refresh_token(user.id, new_refresh)

    return new_access, new_refresh
