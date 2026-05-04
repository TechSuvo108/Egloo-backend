from uuid import UUID
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.models.query_history import QueryHistory


async def save_query(
    db: AsyncSession,
    user_id: UUID,
    question: str,
    answer: str,
    sources_used: List[dict],
    model_used: str,
) -> QueryHistory:
    """Save a completed query + answer to PostgreSQL history."""
    record = QueryHistory(
        user_id=user_id,
        question=question,
        answer=answer,
        sources_used=sources_used,
        model_used=model_used,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_query_history(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> List[QueryHistory]:
    """Get paginated query history for a user."""
    result = await db.execute(
        select(QueryHistory)
        .where(QueryHistory.user_id == user_id)
        .order_by(desc(QueryHistory.created_at))
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def delete_query_history(
    db: AsyncSession,
    user_id: UUID,
) -> int:
    """Delete all query history for a user. Returns count deleted."""
    from sqlalchemy import delete, func, select as sel
    count_result = await db.execute(
        sel(func.count()).select_from(QueryHistory)
        .where(QueryHistory.user_id == user_id)
    )
    count = count_result.scalar()
    await db.execute(
        delete(QueryHistory).where(QueryHistory.user_id == user_id)
    )
    await db.commit()
    return count
