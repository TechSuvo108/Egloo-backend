from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.brain import BrainTodayResponse, BrainMissingResponse, BrainConnectionsResponse
from app.services import brain_service, alert_service

router = APIRouter(tags=["Brain"])

@router.get("/today", response_model=BrainTodayResponse)
async def get_today_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a proactive summary of your priorities, blockers, and action items
    based on the last 7 days of activity across all sources.
    """
    try:
        result = await brain_service.get_brain_today(db, current_user.id)
        return BrainTodayResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pingo could not generate your brain summary: {str(e)}"
        )

@router.post("/missing", response_model=BrainMissingResponse)
async def get_missing_items(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyzes your recent data to find unresolved tasks, unanswered messages,
    missed deadlines, or pending approvals.
    """
    try:
        result = await brain_service.get_missing_items(db, current_user.id)
        return BrainMissingResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pingo could not analyze missing items: {str(e)}"
        )
@router.get("/alerts", response_model=list)
async def get_alerts(
    current_user: User = Depends(get_current_user),
):
    """
    Get the list of urgent alerts found during ingestion (e.g. deadlines, blockers).
    """
    return await alert_service.get_alerts(str(current_user.id))

@router.delete("/alerts", response_model=dict)
async def clear_alerts(
    current_user: User = Depends(get_current_user),
):
    """Clear all proactive alerts."""
    await alert_service.clear_alerts(str(current_user.id))
    return {"message": "Alerts cleared."}

@router.get("/connections", response_model=BrainConnectionsResponse)
async def get_brain_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get semantically discovered connections between different data sources.
    Connects related information from PDFs, Emails, Slack, etc.
    """
    try:
        result = await brain_service.get_brain_connections(db, current_user.id)
        return BrainConnectionsResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pingo could not discover connections: {str(e)}"
        )
