from fastapi import APIRouter, Depends, HTTPException, Query as QueryParam
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.query import (
    AskRequest, AskResponse,
    QueryHistoryResponse, QueryHistoryItem,
)
from app.ai.rag_service import answer_question, answer_question_stream
from app.services.query_history_service import (
    save_query, get_query_history, delete_query_history,
)

router = APIRouter(prefix="/query", tags=["query"])


@router.post("/ask", response_model=AskResponse)
async def ask(
    body: AskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Ask PenGo a question about your data.
    Returns complete answer with source citations.
    Checks Redis cache first — cached answers return instantly.
    """
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if len(body.question) > 1000:
        raise HTTPException(
            status_code=400,
            detail="Question too long. Keep it under 1000 characters."
        )

    try:
        result = await answer_question(
            user_id=str(current_user.id),
            question=body.question,
            use_cache=body.use_cache,
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"PenGo encountered an error: {str(e)}",
        )

    # Save to history (non-blocking — don't fail if save fails)
    try:
        await save_query(
            db=db,
            user_id=current_user.id,
            question=body.question,
            answer=result["answer"],
            sources_used=result["sources"],
            model_used=result["model_used"],
        )
    except Exception as e:
        print(f"[WARNING] Failed to save query history: {e}")

    return AskResponse(**result)


@router.post("/ask/stream")
async def ask_stream(
    body: AskRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Ask PenGo a question — answer streams token by token via SSE.

    Frontend connects with EventSource or fetch + ReadableStream.
    Events:
      {type: "sources", sources: [...]}  ← arrives first
      {type: "token",   token: "Hello"}  ← one per token
      {type: "done",    model: "gemini"} ← final event
      [DONE]                             ← stream closed

    Android client: use Ktor SSE client to consume this stream.
    """
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    return StreamingResponse(
        answer_question_stream(
            user_id=str(current_user.id),
            question=body.question,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/history", response_model=QueryHistoryResponse)
async def get_history(
    limit: int = QueryParam(default=20, ge=1, le=100),
    offset: int = QueryParam(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get paginated query history for the current user.
    Shows past questions and PenGo's answers.
    """
    history = await get_query_history(
        db, current_user.id, limit=limit, offset=offset
    )
    return QueryHistoryResponse(
        history=[QueryHistoryItem.model_validate(h) for h in history],
        total=len(history),
    )


@router.delete("/history", response_model=dict)
async def clear_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clear all query history for the current user."""
    count = await delete_query_history(db, current_user.id)
    return {
        "message": f"Cleared {count} query records. PenGo forgot everything."
    }


@router.get("/suggest", response_model=dict)
async def get_suggestions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return suggested questions based on what data the user has ingested.
    Static suggestions for now — dynamic ones added in Step 9.
    """
    suggestions = [
        "What are my pending action items?",
        "What did my team decide this week?",
        "Summarize the most important emails from today",
        "What projects are currently in progress?",
        "Are there any deadlines I should know about?",
        "What was discussed in Slack about the product launch?",
        "Who has been trying to reach me?",
        "What documents were recently updated?",
    ]
    return {"suggestions": suggestions}
