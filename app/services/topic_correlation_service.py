import asyncio
from typing import List, Dict, Any
from app.ai.rag_service import retrieve_chunks
from app.ai.topic_ai import cluster_chunks

async def correlate_topics(
    user_id: str, 
    recent_chunks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Topic Correlation Layer: Connects related chunks across sources.
    
    Flow:
    1. Takes a set of recent chunks.
    2. Performs semantic expansion using ChromaDB to find related historical context.
    3. Groups the results into thematic clusters (topics).
    
    Example: 
    If a recent email mentions "PDF upload", this layer finds 
    related Slack messages and Drive docs to create a "PDF Upload Feature" cluster.
    """
    if not recent_chunks:
        return []

    # ── Step 1: Normalize incoming chunks ─────────────────────────────────────
    # Ensure they have the format expected by cluster_chunks (topic_ai.py)
    normalized_recent = []
    for c in recent_chunks:
        meta = c.get("chunk_metadata") or c.get("metadata") or {}
        normalized_recent.append({
            "content": c.get("content", ""),
            "chunk_metadata": meta,
            "id": c.get("id") or c.get("document_id"),
            "source_type": c.get("source_type") or meta.get("source_type", "unknown"),
            "sender": c.get("sender") or meta.get("sender", ""),
            "subject": c.get("subject") or meta.get("subject", ""),
            "timestamp": c.get("timestamp") or meta.get("timestamp", ""),
        })

    # ── Step 2: Semantic Expansion (Connect the Dots) ─────────────────────────
    # For the top most relevant recent items, find related items in ChromaDB
    expansion_tasks = []
    # Only expand for a subset to avoid excessive queries/token use
    for c in normalized_recent[:15]: 
        content = c["content"]
        if len(content) > 30:
            expansion_tasks.append(retrieve_chunks(user_id, content, top_k=2))
    
    if expansion_tasks:
        expansion_results = await asyncio.gather(*expansion_tasks)
    else:
        expansion_results = []
    
    # ── Step 3: Pool and Deduplicate ──────────────────────────────────────────
    # We use a dict keyed by content hash or ID to deduplicate
    pool: Dict[str, Dict[str, Any]] = {}
    
    for c in normalized_recent:
        key = c.get("id") or hash(c["content"])
        pool[str(key)] = c
        
    for res_list in expansion_results:
        for c in res_list:
            # Normalize expanded chunks too
            meta = c.get("metadata") or {}
            norm_c = {
                "content": c["content"],
                "chunk_metadata": meta,
                "id": c.get("document_id"),
                "source_type": c.get("source_type") or meta.get("source_type", "unknown"),
                "sender": c.get("sender") or meta.get("sender", ""),
                "subject": c.get("subject") or meta.get("subject", ""),
                "timestamp": c.get("timestamp") or meta.get("timestamp", ""),
            }
            key = norm_c.get("id") or hash(norm_c["content"])
            if str(key) not in pool:
                pool[str(key)] = norm_c
    
    all_chunks = list(pool.values())

    # ── Step 4: Semantic Grouping ─────────────────────────────────────────────
    # Use existing clustering logic (auto-switches between LLM and KMeans)
    clusters = await cluster_chunks(
        all_chunks, 
        strategy="auto", 
        max_topics=8
    )
    
    # ── Step 5: Format Clusters ───────────────────────────────────────────────
    grouped_topics = []
    for cluster in clusters:
        indices = cluster.get("chunk_indices", [])
        if not indices:
            continue
            
        cluster_chunks_list = [all_chunks[i] for i in indices if i < len(all_chunks)]
        
        grouped_topics.append({
            "name": cluster.get("name", "Unnamed Topic"),
            "summary": cluster.get("summary", ""),
            "chunks": cluster_chunks_list,
            "source_types": cluster.get("source_types", [])
        })
        
    return grouped_topics
