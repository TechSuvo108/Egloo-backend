import asyncio
import hashlib
from typing import List, Dict, Any
from app.ai.rag_service import retrieve_chunks
from app.ai.topic_ai import cluster_chunks

URGENCY_TAGS = ["urgent", "blocked", "pending", "deadline"]
KEYWORD_WEIGHTS = ["parser", "upload", "auth", "approval", "meeting", "payment"]

def _get_content_hash(text: str) -> str:
    """Simple hash for deduplication."""
    return hashlib.sha256(text.encode()).hexdigest()

def _is_noise(text: str) -> bool:
    """Basic filter for noise like resumes or generic profiles."""
    text_lower = text.lower()
    noise_indicators = ["resume", "cv", "portfolio", "objective:", "skills:", "experience:"]
    # If more than 3 indicators present, likely a resume
    hits = sum(1 for indicator in noise_indicators if indicator in text_lower)
    return hits >= 3

async def correlate_topics(
    user_id: str, 
    recent_chunks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Improved Topic Correlation Layer:
    Connects related chunks across sources with noise filtering and importance weighting.
    """
    if not recent_chunks:
        return []

    initial_count = len(recent_chunks)

    # ── Step 1: Filter Noise and Stale Data ───────────────────────────────────
    # Requirement: Last 7 days and skip noise
    # Note: caller (brain_service) already filters by 7 days in the DB query, 
    # but we double check here if timestamp exists.
    filtered = []
    for c in recent_chunks:
        content = c.get("content", "")
        if _is_noise(content):
            continue
        filtered.append(c)
    
    print(f"[BRAIN] filtered {initial_count - len(filtered)} noise chunks")

    # ── Step 2: Normalize and Weight ──────────────────────────────────────────
    normalized = []
    for c in filtered:
        meta = c.get("chunk_metadata") or c.get("metadata") or {}
        content = c.get("content", "")
        content_lower = content.lower()
        
        # Calculate importance score
        score = 0
        if any(tag in content_lower for tag in URGENCY_TAGS):
            score += 10
        if any(kw in content_lower for kw in KEYWORD_WEIGHTS):
            score += 5
            
        normalized.append({
            "content": content,
            "chunk_metadata": meta,
            "id": c.get("id") or c.get("document_id"),
            "source_type": c.get("source_type") or meta.get("source_type", "unknown"),
            "sender": meta.get("sender", ""),
            "subject": meta.get("subject", ""),
            "timestamp": meta.get("timestamp", ""),
            "importance": score
        })

    # ── Step 3: Semantic Expansion (Connect the Dots) ─────────────────────────
    # Expand only for high importance or very relevant items
    # Sort by importance first
    normalized.sort(key=lambda x: x["importance"], reverse=True)
    
    expansion_tasks = []
    for c in normalized[:10]: # Expand top 10 important items
        content = c["content"]
        if len(content) > 30:
            expansion_tasks.append(retrieve_chunks(user_id, content, top_k=2))
    
    expansion_results = await asyncio.gather(*expansion_tasks) if expansion_tasks else []

    # ── Step 4: Pool and Dedup ────────────────────────────────────────────────
    # Requirement: Remove duplicate / near-duplicate chunks
    pool: Dict[str, Dict[str, Any]] = {}
    
    def add_to_pool(chunk_list, is_expansion=False):
        for c in chunk_list:
            if is_expansion:
                # Normalize expansion result format
                meta = c.get("metadata") or {}
                norm_c = {
                    "content": c["content"],
                    "chunk_metadata": meta,
                    "id": c.get("document_id"),
                    "source_type": c.get("source_type") or meta.get("source_type", "unknown"),
                    "sender": meta.get("sender", ""),
                    "subject": meta.get("subject", ""),
                    "timestamp": meta.get("timestamp", ""),
                    "importance": 0
                }
            else:
                norm_c = c
                
            # Content-based dedup
            h = _get_content_hash(norm_c["content"])
            if h not in pool:
                pool[h] = norm_c

    add_to_pool(normalized)
    for res_list in expansion_results:
        add_to_pool(res_list, is_expansion=True)
    
    all_chunks = list(pool.values())
    print(f"[BRAIN] deduped to {len(all_chunks)} chunks")

    # ── Step 5: Semantic Grouping ─────────────────────────────────────────────
    # Better cluster naming and size limit is handled inside topic_ai.py
    # but we can pass max_topics and max_topics here
    clusters = await cluster_chunks(
        all_chunks, 
        strategy="auto", 
        max_topics=6 # Limit to fewer, cleaner topics
    )
    
    # ── Step 6: Format ────────────────────────────────────────────────────────
    grouped_topics = []
    for cluster in clusters:
        indices = cluster.get("chunk_indices", [])
        if not indices:
            continue
            
        cluster_chunks_list = [all_chunks[i] for i in indices if i < len(all_chunks)]
        
        # Limit cluster size to top relevant items (e.g., 10 per cluster)
        cluster_chunks_list = cluster_chunks_list[:10]

        grouped_topics.append({
            "name": cluster.get("name", "Unnamed Topic"),
            "summary": cluster.get("summary", ""),
            "chunks": cluster_chunks_list,
            "source_types": cluster.get("source_types", [])
        })
    
    print(f"[BRAIN] clustered into {len(grouped_topics)} clean topics")
    return grouped_topics
