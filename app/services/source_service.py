"""
CRUD helpers for the DataSource model (data_sources table).
All token values are Fernet-encrypted before being written to the DB and
decrypted on read.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import DataSource
from app.utils.encryption import encrypt_token, decrypt_token


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

async def get_source_by_type(
    db: AsyncSession,
    user_id: UUID,
    source_type: str,
) -> Optional[DataSource]:
    """Return the DataSource row for a specific user + source_type, or None."""
    result = await db.execute(
        select(DataSource).where(
            DataSource.user_id == user_id,
            DataSource.source_type == source_type,
        )
    )
    return result.scalar_one_or_none()


async def get_all_sources(
    db: AsyncSession,
    user_id: UUID,
) -> list[DataSource]:
    """Return all DataSource rows for a user."""
    result = await db.execute(
        select(DataSource).where(DataSource.user_id == user_id)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

async def upsert_source(
    db: AsyncSession,
    user_id: UUID,
    source_type: str,
    access_token: str,
    refresh_token: Optional[str],
    token_expiry: Optional[datetime],
    source_metadata: Optional[dict] = None,
) -> DataSource:
    """Create or update a DataSource row for *user_id* + *source_type*.

    Tokens are encrypted with Fernet before being persisted.
    """
    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = encrypt_token(refresh_token) if refresh_token else None

    source = await get_source_by_type(db, user_id, source_type)

    if source is None:
        source = DataSource(
            user_id=user_id,
            source_type=source_type,
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            token_expiry=token_expiry,
            sync_status="idle",
            source_metadata=source_metadata or {},
        )
        db.add(source)
    else:
        source.access_token = encrypted_access
        source.refresh_token = encrypted_refresh
        source.token_expiry = token_expiry
        source.sync_status = "idle"
        if source_metadata is not None:
            source.source_metadata = source_metadata

    await db.commit()
    await db.refresh(source)
    return source


async def delete_source(
    db: AsyncSession,
    user_id: UUID,
    source_type: str,
) -> bool:
    """Delete a DataSource row. Returns True if a row was deleted, False otherwise."""
    result = await db.execute(
        delete(DataSource).where(
            DataSource.user_id == user_id,
            DataSource.source_type == source_type,
        )
    )
    await db.commit()
    return result.rowcount > 0


# ---------------------------------------------------------------------------
# Token decryption helper (used by sync workers)
# ---------------------------------------------------------------------------

def get_decrypted_access_token(source: DataSource) -> Optional[str]:
    """Decrypt and return the stored access token, or None if not set."""
    if source.access_token is None:
        return None
    return decrypt_token(source.access_token)


def get_decrypted_refresh_token(source: DataSource) -> Optional[str]:
    """Decrypt and return the stored refresh token, or None if not set."""
    if source.refresh_token is None:
        return None
    return decrypt_token(source.refresh_token)
