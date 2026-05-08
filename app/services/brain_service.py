import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.document_chunk import DocumentChunk
from app.ai.llm_router import call_llm_simple, hash_query
from app.ai.rag_service import build_context
from app.services.topic_correlation_service import correlate_topics
from app.utils.redis_client import get_redis_client

def get_redis(): return get_redis_client()

# ─── System Prompt for Brain Intelligence ─────────────────────────────────────

BRAIN_SYSTEM_PROMPT = """You are the Proactive Intelligence module for Egloo.
Your job is to analyze recent communications and documents to provide a clear,
actionable executive summary for the user.

Your goal is to help the user stay on top of their work without having to dig
through every email and Slack message.

Rules:
1. Always ground your analysis in the provided context.
2. If the context is empty, state that there is no recent data to analyze.
3. Return your response in the EXACT JSON format requested.
4. Do not include any text outside of the JSON block."""


# ─── Internal Helper: Extract JSON from LLM response ──────────────────────────

def _extract_json(text: str) -> Dict[str, Any]:
    """
    Attempts to parse JSON from LLM response. 
    Handles cases where the LLM might wrap JSON in markdown blocks.
    """
    text = text.strip()
    if text.startswith("```json"):
        text = text.replace("```json", "", 1)
    if text.endswith("```"):
        text = text[: -3]
    text = text.strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: find the first { and last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end+1])
            except:
                pass
        return {"error": "Failed to parse intelligence response", "raw": text}


# ─── Function 1: Daily Brain (Proactive Summary) ──────────────────────────────

async def get_brain_today(
    db: AsyncSession, 
    user_id: UUID,
    days: int = 7
) -> Dict[str, Any]:
    """
    Collects chunks from the last N days and generates a 
    structured proactive summary of priorities and blockers.
    """
    # 0. Check Cache
    cache_key = f"brain_today:{user_id}"
    cached = await get_redis().get(cache_key)
    if cached:
        return json.loads(cached)

    # 1. Fetch recent chunks from PostgreSQL
    # (ChromaDB is for semantic search, Postgres is better for temporal aggregation)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.user_id == user_id)
        .where(DocumentChunk.created_at >= since)
        .order_by(desc(DocumentChunk.created_at))
        .limit(100) # Limit to avoid context window overflow
    )
    db_chunks = result.scalars().all()
    
    if not db_chunks:
        return {
            "priorities": [],
            "blocked": [],
            "action_items": [],
            "suggested_first_step": "No recent data found in the last 7 days. Try connecting more sources or syncing your data."
        }

    # 2. Format chunks for the LLM
    # We map Postgres models to the dict format build_context expects
    formatted_chunks = []
    for c in db_chunks:
        meta = c.chunk_metadata or {}
        formatted_chunks.append({
            "content": c.content,
            "source_type": meta.get("source_type", "unknown"),
            "sender": meta.get("sender", ""),
            "subject": meta.get("subject", ""),
            "timestamp": meta.get("timestamp", ""),
            "metadata": meta,
            "filename": meta.get("filename", ""),
            "page_number": meta.get("page_number", "")
        })
    
    # 2. Correlate topics (Connect the dots across sources)
    # This groups related chunks into thematic clusters
    clusters = await correlate_topics(str(user_id), formatted_chunks)
    
    if clusters:
        # Build context from clusters
        context_parts = []
        for cluster in clusters:
            cluster_text = f"TOPIC: {cluster['name']}\n"
            cluster_text += f"SUMMARY: {cluster['summary']}\n"
            cluster_text += build_context(cluster['chunks'])
            context_parts.append(cluster_text)
        context = "\n\n===\n\n".join(context_parts)
    else:
        # Fallback to flat context if clustering failed
        context = build_context(formatted_chunks)

    # 3. Build Prompt
    prompt = f"""Based on the following recent activity and correlated topics from the last {days} days, 
provide a structured intelligence summary.

RECENT ACTIVITY & CORRELATED TOPICS:
{context}

---

Return a JSON object with the following structure:
{{
  "priorities": ["list of top 3 high-level priorities found"],
  "blocked": ["list of items where the user is waiting on someone or something"],
  "action_items": ["list of specific tasks for the user"],
  "suggested_first_step": "A single sentence recommending what the user should do right now"
}}"""

    # 4. Call LLM Router
    answer, model = await call_llm_simple(
        prompt=prompt,
        system=BRAIN_SYSTEM_PROMPT
    )

    # 5. Parse and return
    intelligence = _extract_json(answer)
    intelligence["model_used"] = model
    
    # 6. Cache for 1 hour
    await get_redis().setex(cache_key, 3600, json.dumps(intelligence))
    
    return intelligence


async def get_brain_connections(
    db: AsyncSession, 
    user_id: UUID,
    days: int = 7
) -> Dict[str, Any]:
    """
    Brain Connection Engine:
    1. Fetches chunks from the last 7 days.
    2. Performs topic correlation (cross-source clustering).
    3. Uses LLM to summarize connections and assess urgency.
    """
    # 0. Check Cache
    cache_key = f"brain_connections:{user_id}"
    cached = await get_redis().get(cache_key)
    if cached:
        return json.loads(cached)

    print(f"[BRAIN] Connecting dots for user {user_id} over the last {days} days...")

    # 1. Fetch chunks
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.user_id == user_id)
        .where(DocumentChunk.created_at >= since)
        .order_by(desc(DocumentChunk.created_at))
        .limit(150)
    )
    db_chunks = result.scalars().all()
    print(f"[BRAIN] fetched {len(db_chunks)} chunks")

    if not db_chunks:
        return {"connections": []}

    # 2. Format
    formatted_chunks = []
    for c in db_chunks:
        meta = c.chunk_metadata or {}
        formatted_chunks.append({
            "content": c.content,
            "source_type": meta.get("source_type", "unknown"),
            "sender": meta.get("sender", ""),
            "subject": meta.get("subject", ""),
            "timestamp": meta.get("timestamp", ""),
            "metadata": meta
        })

    # 3. Correlate Topics
    clusters = await correlate_topics(str(user_id), formatted_chunks)
    print(f"[BRAIN] clustered into {len(clusters)} topics")

    if not clusters:
        return {"connections": []}

    # 4. Generate Connections via LLM
    # We'll process each cluster to find "Connections"
    connections = []
    model_used = "unknown"

    for cluster in clusters:
        context = build_context(cluster["chunks"])
        
        prompt = f"""You are the Connection Engine for Egloo. 
Analyze these related pieces of information from DIFFERENT sources (Email, Slack, PDF, etc.) 
and describe how they connect.

CONTEXT FOR THIS TOPIC ({cluster['name']}):
{context}

---

Return a JSON object:
{{
  "topic": "Concise topic name",
  "related_sources": ["List unique source types found, e.g., 'Gmail', 'Slack'"],
  "urgency_score": 1-10,
  "suggested_action": "Specific next step for the user",
  "summary": "1-2 sentence explanation of how these different sources connect"
}}"""

        answer, model = await call_llm_simple(
            prompt=prompt,
            system="Return EXACT JSON as requested. Be concise."
        )
        model_used = model
        conn = _extract_json(answer)
        if "topic" in conn:
            connections.append(conn)

    final_result = {
        "connections": connections,
        "model_used": model_used
    }
    
    print(f"[BRAIN] generated {len(connections)} connections")

    # Cache for 1 hour
    await get_redis().setex(cache_key, 3600, json.dumps(final_result))
    return final_result


# ─── Function 4: Brain Health Check ──────────────────────────────────────────

async def check_brain_health(db: AsyncSession) -> Dict[str, Any]:
    """
    Checks connectivity for all critical brain dependencies.
    """
    import sqlalchemy
    from app.utils.chroma_client import get_chroma_client
    from datetime import datetime, timezone
    from app.ai.llm_router import get_active_provider_async
    
    print("[BRAIN HEALTH] Performing health check...")
    
    health = {
        "postgres": False,
        "redis": False,
        "chroma": False,
        "llm": "none",
        "scheduler": False,
    }
    
    # 1. Postgres
    try:
        await db.execute(sqlalchemy.text("SELECT 1"))
        health["postgres"] = True
    except Exception as e:
        print(f"[BRAIN HEALTH] Postgres error: {e}")

    # 2. Redis
    try:
        r = get_redis()
        await r.ping()
        health["redis"] = True
    except Exception as e:
        print(f"[BRAIN HEALTH] Redis error: {e}")

    # 3. Chroma
    try:
        get_chroma_client().heartbeat()
        health["chroma"] = True
    except Exception as e:
        print(f"[BRAIN HEALTH] Chroma error: {e}")

    # 4. LLM
    try:
        health["llm"] = await get_active_provider_async()
    except Exception as e:
        print(f"[BRAIN HEALTH] LLM check error: {e}")

    # 5. Scheduler (check heartbeat)
    if health["redis"]:
        try:
            last_beat = await get_redis().get("scheduler_last_heartbeat")
            if last_beat:
                # If heartbeat was within the last 3 minutes, it's alive
                last_time = datetime.fromisoformat(last_beat.decode() if isinstance(last_beat, bytes) else last_beat)
                diff = datetime.now(timezone.utc) - last_time
                if diff.total_seconds() < 180:
                    health["scheduler"] = True
        except Exception as e:
            print(f"[BRAIN HEALTH] Scheduler check error: {e}")

    # Calculate overall status
    critical_ok = health["postgres"] and health["redis"]
    if critical_ok:
        if health["chroma"] and health["scheduler"] and health["llm"] != "none":
            status = "healthy"
        else:
            status = "degraded"
    else:
        status = "down"
        
    health["status"] = status
    print(f"[BRAIN HEALTH] Result: {status}")
    return health
