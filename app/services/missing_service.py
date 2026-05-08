import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_chunk import DocumentChunk
from app.ai.llm_router import call_llm_simple
from app.ai.rag_service import build_context
from app.services.alert_service import get_alerts
from app.utils.redis_client import get_redis_client

def get_redis(): return get_redis_client()

MISSING_SYSTEM_PROMPT = """You are the Gap Analysis Engine for Egloo.
Your job is to find what's "missing" or "pending" in the user's digital life.
Analyze recent activity and proactive alerts to identify:
- Unanswered urgent requests
- Pending approvals the user needs to give
- Unresolved blockers
- Missed follow-ups from the user or others
- Approaching deadlines

Rules:
1. Ground your analysis in the provided context.
2. Be specific but concise.
3. Return your response in the EXACT JSON format requested.
"""

async def get_missing_items(
    db: AsyncSession, 
    user_id: UUID,
    days: int = 7
) -> Dict[str, Any]:
    """
    Analyzes recent chunks and proactive alerts to find missing follow-ups,
    unanswered questions, and pending tasks.
    """
    # 0. Check Cache
    cache_key = f"brain_missing_v2:{user_id}"
    cached = await get_redis().get(cache_key)
    if cached:
        return json.loads(cached)

    print(f"[MISSING] Analyzing gaps for user {user_id}...")

    # 1. Fetch recent chunks (last 7 days)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.user_id == user_id)
        .where(DocumentChunk.created_at >= since)
        .order_by(desc(DocumentChunk.created_at))
        .limit(100)
    )
    db_chunks = result.scalars().all()
    print(f"[MISSING] fetched {len(db_chunks)} chunks")

    # 2. Fetch alerts from Redis
    alerts = await get_alerts(str(user_id))
    
    # 3. Combine Context
    formatted_chunks = []
    for c in db_chunks:
        meta = c.chunk_metadata or {}
        formatted_chunks.append({
            "content": c.content,
            "source_type": meta.get("source_type", "unknown"),
            "sender": meta.get("sender", ""),
            "subject": meta.get("subject", ""),
            "metadata": meta
        })
    
    activity_context = build_context(formatted_chunks)
    
    alert_context = ""
    if alerts:
        alert_context = "RECENT PROACTIVE ALERTS:\n"
        for a in alerts:
            alert_context += f"- [{a.get('type')}] {a.get('message')}\n"

    full_context = f"{activity_context}\n\n{alert_context}"

    # 4. Prompt LLM
    prompt = f"""Based on the following recent activity and alerts from the last {days} days, 
identify any missing information, pending follow-ups, or unresolved items.

CONTEXT:
{full_context}

---

Return a JSON object with the following structure:
{{
  "missing": [
    "Brief description of item 1",
    "Brief description of item 2"
  ]
}}"""

    answer, model = await call_llm_simple(
        prompt=prompt,
        system=MISSING_SYSTEM_PROMPT
    )

    # 5. Parse
    try:
        # Simple extraction helper (reused from brain_service logic)
        import re
        json_match = re.search(r"\{.*\}", answer, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            result = {"missing": []}
    except:
        result = {"missing": []}
    
    if "missing" not in result:
        result["missing"] = []
    
    result["model_used"] = model
    print(f"[MISSING] found {len(result['missing'])} missing items")

    # 6. Cache for 1 hour
    await get_redis().setex(cache_key, 3600, json.dumps(result))
    
    return result
