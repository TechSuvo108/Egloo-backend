import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.config import settings
from app.utils.redis_client import get_redis_client

def get_redis(): return get_redis_client()

# Jobs live in Redis for 24 hours
JOB_TTL_SECONDS = 86400


async def create_job(
    job_id: str,
    user_id: str,
    source_id: str,
    source_type: str,
) -> Dict[str, Any]:
    """
    Create a new job record in Redis when a task is queued.
    Status lifecycle: queued -> started -> success | failed
    """
    job: Dict[str, Any] = {
        "job_id": job_id,
        "user_id": user_id,
        "source_id": source_id,
        "source_type": source_type,
        "status": "queued",
        "progress": 0,
        "message": "Job queued. Pingo is getting ready...",
        "result": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    key = f"job:{job_id}"
    await get_redis().setex(key, JOB_TTL_SECONDS, json.dumps(job))
    return job


async def update_job(
    job_id: str,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    result: Optional[Dict] = None,
    error: Optional[str] = None,
) -> None:
    """Update job status in Redis. Call this from inside Celery tasks."""
    key = f"job:{job_id}"
    raw = await get_redis().get(key)
    if not raw:
        return

    job: Dict[str, Any] = json.loads(raw)
    if status is not None:
        job["status"] = status
    if progress is not None:
        job["progress"] = progress
    if message is not None:
        job["message"] = message
    if result is not None:
        job["result"] = result
    if error is not None:
        job["error"] = error
    job["updated_at"] = datetime.now(timezone.utc).isoformat()

    await get_redis().setex(key, JOB_TTL_SECONDS, json.dumps(job))


async def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Fetch job status from Redis."""
    key = f"job:{job_id}"
    raw = await get_redis().get(key)
    if not raw:
        return None
    return json.loads(raw)


async def get_user_jobs(user_id: str, limit: int = 20) -> list:
    """
    Get all recent jobs for a user.
    Scans Redis for keys matching job:* and filters by user_id.
    """
    jobs = []
    async for key in get_redis().scan_iter("job:*"):
        raw = await get_redis().get(key)
        if raw:
            job: Dict[str, Any] = json.loads(raw)
            if job.get("user_id") == user_id:
                jobs.append(job)

    # Sort by created_at descending
    jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return jobs[:limit]
