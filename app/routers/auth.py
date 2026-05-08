from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import (
    UserRegister,
    UserLogin,
    UserResponse,
    TokenResponse,
    RefreshTokenRequest,
    MessageResponse,
)
from app.services.auth_service import (
    register_user,
    login_user,
    refresh_access_token,
    blacklist_access_token,
)
from app.utils.redis_client import get_redis_client
from app.dependencies import get_current_user
from app.models.user import User
from app.config import settings

router = APIRouter(prefix="/auth", tags=["🐧 Auth"])
bearer_scheme = HTTPBearer()


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user and receive access + refresh tokens."""
    try:
        access_token, refresh_token, user = await register_user(
            db, body.email, body.password, body.full_name
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate with email and password, receive tokens."""
    try:
        access_token, refresh_token, user = await login_user(
            db, body.email, body.password
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    try:
        new_access, new_refresh = await refresh_access_token(body.refresh_token, db)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    current_user: User = Depends(get_current_user),
):
    """Blacklist the current access token and delete the refresh token from Redis."""
    token = credentials.credentials
    ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    await blacklist_access_token(token, ttl)
    await get_redis_client().delete(f"refresh_token:{str(current_user.id)}")
    return MessageResponse(message="Successfully logged out. Pingo is taking a nap. 🐧")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user
