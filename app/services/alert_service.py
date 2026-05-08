import json
from datetime import datetime, timezone
from typing import List, Dict, Any
from app.config import settings
from app.utils.redis_client import get_redis_client

def get_redis(): return get_redis_client()

URGENCY_KEYWORDS = [
    "urgent", "deadline", "asap", "blocked", 
    "waiting", "pending", "tomorrow", "approval"
]

async def scan_and_store_alerts(user_id: str, chunks: List[Dict[str, Any]]):
    """
    Scans new chunks for urgency keywords and stores proactive alerts in Redis.
    """
    alerts = []
    
    print(f"[ALERT] Scanning {len(chunks)} chunks for user {user_id}...")
    
    for chunk in chunks:
        content = chunk.get("content", "").lower()
        metadata = chunk.get("metadata", {})
        source_type = metadata.get("source_type", "unknown").upper()
        
        # Check for keywords
        found_keywords = [k for k in URGENCY_KEYWORDS if k in content]
        
        if found_keywords:
            print(f"[ALERT] Matched keywords {found_keywords} in {source_type} chunk")
            # Create a succinct alert message
            subject = metadata.get("subject") or metadata.get("filename") or "item"
            keyword_str = ", ".join(found_keywords)
            
            message = f"{source_type} {keyword_str}: {subject}"
            
            alerts.append({
                "type": "urgent",
                "message": message,
                "keywords": found_keywords,
                "source": source_type,
                "document_id": metadata.get("document_id"),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

    if not alerts:
        return

    # Store in Redis: alerts:{user_id}
    # We use a list to store multiple alerts, or just overwrite? 
    # User said "Format: [{...}]" which implies a list.
    # We'll prepend new alerts to the list and keep the last 50.
    
    cache_key = f"alerts:{user_id}"
    
    # Get existing alerts
    existing_raw = await get_redis().get(cache_key)
    existing_alerts = json.loads(existing_raw) if existing_raw else []
    
    # Combine (new first) and limit to 50
    all_alerts = alerts + existing_alerts
    all_alerts = all_alerts[:50]
    
    await get_redis().set(cache_key, json.dumps(all_alerts))
    print(f"[ALERT] Saved {len(alerts)} alerts for user {user_id} (Total in Redis: {len(all_alerts)})")

async def get_alerts(user_id: str) -> List[Dict[str, Any]]:
    """Retrieve alerts from Redis."""
    cache_key = f"alerts:{user_id}"
    raw = await get_redis().get(cache_key)
    return json.loads(raw) if raw else []

async def clear_alerts(user_id: str):
    """Clear alerts for a user."""
    cache_key = f"alerts:{user_id}"
    await get_redis().delete(cache_key)
