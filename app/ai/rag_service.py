import json
import asyncio
from typing import AsyncGenerator, List, Dict, Any, Optional
from datetime import datetime, timezone

from app.config import settings
from app.utils.embedder import embed_single
from app.utils.chroma_client import get_or_create_collection
from app.ai.llm_router import call_llm, call_llm_simple, hash_query
from app.utils.redis_client import get_redis_client

# Local getter to ensure we are loop-safe
def get_redis(): return get_redis_client()

# ─── Constants ──────────────────────────────────────────────────────────────
MIN_SIMILARITY = 0.03


# ─── System prompt for Pingo ──────────────────────────────────────────────────

PINGO_SYSTEM_PROMPT = """You are Pingo, an intelligent personal assistant
for the Egloo second brain app. You help knowledge workers understand
and act on information from their emails, Slack messages, and documents.

Your personality:
- Clear, concise, and actionable
- You always ground your answers in the provided context
- You never make up information not found in the context
- You cite which source (Gmail, Slack, Drive) each piece of information came from
- If the context does not contain enough information to answer, say so clearly

When answering:
- Lead with the most important information first
- Extract action items when relevant
- Mention the source type and approximate date when available
- Keep answers focused and useful for a busy professional"""


# ─── Step 1: Retrieve relevant chunks from ChromaDB ──────────────────────────

async def retrieve_chunks(
    user_id: str,
    question: str,
    active_sources: List[str] = None,
    top_k: int = None,
) -> List[Dict[str, Any]]:
    """
    Embed the question and search ChromaDB for the
    most semantically relevant chunks for this user.

    Returns list of chunk dicts with content + metadata.
    """
    if top_k is None:
        top_k = settings.RAG_TOP_K

    # Embed the question
    question_vector = embed_single(question)
    print(f"[DEBUG] Question embedded. Vector length: {len(question_vector)}")

    # Get user's ChromaDB collection
    try:
        collection = get_or_create_collection(user_id)
        collection_count = collection.count()
        print(f"[DEBUG] Collection for {user_id} loaded. Total items in collection: {collection_count}")
    except Exception as e:
        print(f"[WARNING] ChromaDB collection error: {e}")
        return []

    # Search for similar chunks
    try:
        # Filter by active sources if provided
        where_filter = None
        if active_sources:
            if len(active_sources) == 1:
                where_filter = {"source_type": active_sources[0]}
            else:
                where_filter = {"source_type": {"$in": active_sources}}
        
        print(f"[DEBUG] Searching ChromaDB with filter: {where_filter}")

        # Run ChromaDB query in a thread pool since the HttpClient is synchronous
        results = await asyncio.to_thread(
            collection.query,
            query_embeddings=[question_vector],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
        print(f"[DEBUG] Raw ChromaDB query results count: {len(results.get('documents', [[]])[0])}")
    except Exception as e:
        print(f"[WARNING] ChromaDB query error: {e}")
        return []

    # Format results
    chunks = []
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for doc, meta, dist in zip(documents, metadatas, distances):
        # Convert cosine distance to similarity score (0-1)
        similarity = round(1 - dist, 4)
        print(f"[DEBUG] Chunk similarity: {similarity} (Distance: {dist})")

        # Only include chunks with reasonable similarity
        if similarity < MIN_SIMILARITY:
            continue

        chunks.append({
            "content": doc,
            "metadata": meta,
            "similarity": similarity,
            "source_type": meta.get("source_type", "unknown"),
            "sender": meta.get("sender", ""),
            "subject": meta.get("subject", ""),
            "timestamp": meta.get("timestamp", ""),
            "document_id": meta.get("document_id", ""),
        })

    # Sort by similarity descending
    chunks.sort(key=lambda x: x["similarity"], reverse=True)

    print(f"[SEARCH] Retrieved {len(chunks)} chunks for query")
    return chunks


# ─── Step 2: Build context string from chunks ────────────────────────────────

def build_context(chunks: List[Dict[str, Any]]) -> str:
    """
    Format retrieved chunks into a readable context block
    for the LLM prompt.
    """
    if not chunks:
        return "No relevant information found in your connected sources."

    lines = []
    for i, chunk in enumerate(chunks, 1):
        source_type = str(chunk.get("source_type", "unknown")).upper()
        sender = chunk.get("sender", "")
        subject = chunk.get("subject", "")
        timestamp = chunk.get("timestamp", "")
        metadata = chunk.get("metadata", {}) or chunk.get("chunk_metadata", {})

        # Format header for this chunk
        header_parts = [f"[{i}] Source: {source_type}"]
        
        if source_type == "PDF_UPLOAD":
            filename = metadata.get("filename", "Unknown PDF")
            page = metadata.get("page_number", "?")
            header_parts.append(f"File: {filename}")
            header_parts.append(f"Page: {page}")
        else:
            if sender:
                header_parts.append(f"From: {sender}")
            if subject:
                header_parts.append(f"Subject: {subject}")
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp)
                    header_parts.append(f"Date: {dt.strftime('%b %d, %Y')}")
                except Exception:
                    pass

        lines.append(" | ".join(header_parts))
        lines.append(chunk["content"])
        lines.append("")

    return "\n".join(lines)


# ─── Step 3: Format sources for API response ─────────────────────────────────

def format_sources(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Format chunks into source citations for the API response.
    Frontend shows these as colored source chips.
    """
    sources = []
    seen = set()

    for chunk in chunks:
        doc_id = chunk.get("document_id", "")
        if doc_id in seen:
            continue
        seen.add(doc_id)

        sources.append({
            "document_id": doc_id,
            "source_type": chunk.get("source_type", "unknown"),
            "sender": chunk.get("sender", ""),
            "subject": chunk.get("subject", "") or (chunk.get("metadata") or {}).get("filename", ""),
            "timestamp": chunk.get("timestamp", ""),
            "page_number": (chunk.get("metadata") or {}).get("page_number"),
            "content_preview": chunk["content"][:200] + "..."
                if len(chunk["content"]) > 200
                else chunk["content"],
            "similarity": chunk.get("similarity", 0),
        })

    return sources


# ─── Step 4: Cache helpers ───────────────────────────────────────────────────

async def get_cached_answer(user_id: str, question: str) -> Optional[Dict]:
    """Check Redis for a cached answer to this question."""
    cache_key = f"query_cache:{user_id}:{hash_query(user_id, question)}"
    raw = await get_redis().get(cache_key)
    if raw:
        print("[CACHE HIT] Cache hit — returning cached answer")
        return json.loads(raw)
    print("[CACHE MISS] No cached answer found")
    return None


async def cache_answer(user_id: str, question: str, answer_data: Dict):
    """Cache an answer in Redis for QUERY_CACHE_TTL seconds."""
    cache_key = f"query_cache:{user_id}:{hash_query(user_id, question)}"
    await get_redis().setex(
        cache_key,
        settings.QUERY_CACHE_TTL,
        json.dumps(answer_data),
    )
    print("[CACHE SAVE] Saved answer to cache")


# ─── Step 5: Full RAG pipeline (non-streaming) ───────────────────────────────

async def answer_question(
    user_id: str,
    question: str,
    active_sources: List[str] = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    Full RAG pipeline — returns complete answer dict.

    Returns:
    {
        "answer": "...",
        "sources": [...],
        "model_used": "gemini",
        "chunks_retrieved": 5,
        "cached": False,
        "question": "...",
    }
    """
    # Check cache first
    if use_cache:
        cached = await get_cached_answer(user_id, question)
        if cached:
            cached["cached"] = True
            return cached

    # --- Parallel Omni-Search Logic ---
    chunks = []
    if active_sources and len(active_sources) > 1:
        # Search each source in parallel to ensure diversity
        tasks = [
            retrieve_chunks(user_id, question, active_sources=[src])
            for src in active_sources
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results, ignoring exceptions
        for res in results:
            if isinstance(res, list):
                chunks.extend(res)
            else:
                print(f"[WARNING] Parallel search task failed: {res}")
        
        # Deduplicate by document_id and sort by similarity
        seen_docs = set()
        unique_chunks = []
        for c in chunks:
            doc_id = c.get("document_id")
            if doc_id not in seen_docs:
                unique_chunks.append(c)
                seen_docs.add(doc_id)
        
        unique_chunks.sort(key=lambda x: x["similarity"], reverse=True)
        chunks = unique_chunks[:settings.RAG_TOP_K]
    else:
        # Single source or all sources in one query
        chunks = await retrieve_chunks(user_id, question, active_sources=active_sources)

    context = build_context(chunks)

    # Build prompt
    prompt = f"""Here is relevant information from your emails,
Slack messages, and documents:

{context}

---

Question: {question}

Please answer based only on the information provided above.
If the information is insufficient, say so clearly."""

    # Call LLM
    full_answer, model_name = await call_llm_simple(
        prompt=prompt,
        system=PINGO_SYSTEM_PROMPT,
    )

    sources = format_sources(chunks)

    result = {
        "answer": full_answer,
        "sources": sources,
        "model_used": model_name,
        "chunks_retrieved": len(chunks),
        "cached": False,
        "question": question,
    }

    # Cache the result
    if use_cache:
        await cache_answer(user_id, question, result)

    return result


# ─── Step 6: Streaming RAG pipeline ─────────────────────────────────────────

async def answer_question_stream(
    user_id: str,
    question: str,
    active_sources: List[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Streaming RAG pipeline — yields SSE-formatted strings.
    Frontend receives tokens as they arrive from the LLM.

    SSE format:
      data: {"type": "sources", "sources": [...]}
      data: {"type": "token", "token": "Hello"}
      data: {"type": "token", "token": " world"}
      data: {"type": "done", "model": "gemini", "chunks": 5}
      data: [DONE]
    """
    # --- Parallel Omni-Search Logic (Streaming) ---
    chunks = []
    if active_sources and len(active_sources) > 1:
        tasks = [
            retrieve_chunks(user_id, question, active_sources=[src])
            for src in active_sources
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if isinstance(res, list):
                chunks.extend(res)
        
        seen_docs = set()
        unique_chunks = []
        for c in chunks:
            doc_id = c.get("document_id")
            if doc_id not in seen_docs:
                unique_chunks.append(c)
                seen_docs.add(doc_id)
        
        unique_chunks.sort(key=lambda x: x["similarity"], reverse=True)
        chunks = unique_chunks[:settings.RAG_TOP_K]
    else:
        chunks = await retrieve_chunks(user_id, question, active_sources=active_sources)

    context = build_context(chunks)
    sources = format_sources(chunks)

    # Send sources immediately so frontend can show them
    # while tokens are still streaming
    yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\\n\\n"

    # Build prompt
    prompt = f"""Here is relevant information from your emails,
Slack messages, and documents:

{context}

---

Question: {question}

Please answer based only on the information provided above."""

    # Stream tokens from LLM
    model_name = "unknown"
    try:
        gen, model_name = await call_llm(
            prompt=prompt,
            system=PINGO_SYSTEM_PROMPT,
            stream=True,
        )

        async for token in gen:
            yield f"data: {json.dumps({'type': 'token', 'token': token})}\\n\\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\\n\\n"

    # Send done signal
    yield f"data: {json.dumps({'type': 'done', 'model': model_name, 'chunks': len(chunks)})}\\n\\n"
    yield "data: [DONE]\\n\\n"
