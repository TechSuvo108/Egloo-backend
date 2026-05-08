import asyncio
import uuid

from celery import Task

from app.workers.celery_app import celery_app


# ─── Loop Management Helper ──────────────────────────────────────────────────

def run_async(coro):
    """
    Helper to run an async coroutine in a synchronous Celery task.
    Ensures that every task gets its own event loop and properly 
    disposes of global async resources (DB engine, Redis client) 
    to avoid 'Event loop is closed' or 'Loop mismatch' errors.
    """
    async def _run_with_cleanup():
        try:
            return await coro
        finally:
            from app.database import dispose_engine
            from app.utils.redis_client import close_redis_client
            try:
                await dispose_engine()
                await close_redis_client()
            except Exception as e:
                print(f"[WARNING] Async cleanup failed: {e}")

    return asyncio.run(_run_with_cleanup())


# ─── Task 1: Sync a single source ────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="app.workers.tasks.sync_source",
    max_retries=3,
    default_retry_delay=60,
)
def sync_source(self, source_id: str, user_id: str, job_id: str):
    """
    Celery task: run full ingestion pipeline for one source.
    Updates job progress in Redis at each step.
    Retries up to 3 times on failure.
    """
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.source_service import get_source_by_id
        from app.services.ingestion_service import ingest_source
        from app.utils.job_tracker import update_job

        await update_job(
            job_id,
            status="started",
            progress=10,
            message="Pingo started fetching your data...",
        )

        async with AsyncSessionLocal() as db:
            try:
                source = await get_source_by_id(
                    db,
                    uuid.UUID(source_id),
                    uuid.UUID(user_id),
                )
                if not source:
                    await update_job(
                        job_id,
                        status="failed",
                        progress=0,
                        error=f"Source {source_id} not found",
                    )
                    return

                await update_job(
                    job_id,
                    progress=20,
                    message=f"Fetching data from {source.source_type}...",
                )

                result = await ingest_source(db, source, user_id)

                await update_job(
                    job_id,
                    status="success",
                    progress=100,
                    message=f"Pingo finished ingesting {source.source_type}!",
                    result=result,
                )

                # Auto-refresh topics after successful ingestion
                refresh_topics_for_user.delay(
                    user_id=user_id,
                    strategy="auto",
                    max_topics=10,
                )
                print(f"[INFO] Queued topic refresh after ingestion")

            except Exception as e:
                await update_job(
                    job_id,
                    status="failed",
                    progress=0,
                    message="Ingestion failed",
                    error=str(e),
                )
                raise

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


# ─── Task 2: Sync all sources for one user ───────────────────────────────────

@celery_app.task(
    bind=True,
    name="app.workers.tasks.sync_all_sources_for_user",
)
def sync_all_sources_for_user(self, user_id: str):
    """
    Celery task: sync all connected sources for a single user.
    Queues individual sync_source tasks for each source.
    """
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.source_service import get_all_sources
        from app.utils.job_tracker import create_job
        import uuid as _uuid

        async with AsyncSessionLocal() as db:
            sources = await get_all_sources(db, _uuid.UUID(user_id))
            for source in sources:
                if source.sync_status == "syncing":
                    continue

                job_id = str(_uuid.uuid4())
                await create_job(
                    job_id=job_id,
                    user_id=user_id,
                    source_id=str(source.id),
                    source_type=source.source_type,
                )

                # Queue individual task for this source
                sync_source.delay(
                    source_id=str(source.id),
                    user_id=user_id,
                    job_id=job_id,
                )
                print(f"[Pingo] Queued sync for {source.source_type} (job: {job_id})")

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


# ─── Task 3: Auto-sync ALL users (Beat schedule every 15 min) ────────────────

@celery_app.task(name="app.workers.tasks.auto_sync_all_users")
def auto_sync_all_users():
    """
    Celery Beat task: runs every 15 minutes automatically.
    Finds all active users and queues sync_all_sources_for_user for each.
    """
    async def _run():
        from app.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.models.user import User

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.is_active == True)
            )
            users = result.scalars().all()
            print(f"[Pingo] Auto-sync: found {len(users)} active users")

            for user in users:
                sync_all_sources_for_user.delay(user_id=str(user.id))
                print(f"  -> Queued sync for user {user.email}")

    try:
        return run_async(_run())
    except Exception as exc:
        # Standard tasks (Beat) don't necessarily need bind=True/retry, 
        # but we keep it consistent.
        print(f"[ERROR] auto_sync_all_users failed: {exc}")
        raise


# ─── Task 4: Generate daily digest for one user ──────────────────────────────

@celery_app.task(
    bind=True,
    name="app.workers.tasks.generate_digest_for_user",
    max_retries=2,
    default_retry_delay=120,
)
def generate_digest_for_user(self, user_id: str, fcm_token: str = None):
    """
    Celery task: generate daily digest for one user.
    Called by Celery Beat at 7 AM UTC every day.
    Also callable manually via API.
    """
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.digest_service import generate_digest

        print(f"[INFO] Celery: generating digest for user {user_id}")
        async with AsyncSessionLocal() as db:
            result = await generate_digest(
                db=db,
                user_id=user_id,
                fcm_token=fcm_token,
            )
            print(
                f"[OK] Celery digest complete: "
                f"{len(result.get('topics', []))} topics, "
                f"{len(result.get('action_items', []))} actions"
            )
            return result

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


# ─── Task 5: Generate digests for ALL users (Beat schedule 7 AM) ─────────────

@celery_app.task(name="app.workers.tasks.generate_digests_for_all_users")
def generate_digests_for_all_users():
    """
    Celery Beat task: runs every day at 7 AM UTC.
    Queues generate_digest_for_user for every active user.
    """
    async def _run():
        from app.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.models.user import User

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.is_active == True)
            )
            users = result.scalars().all()
            print(f"[Pingo] Digest generation: {len(users)} users")

            for user in users:
                generate_digest_for_user.delay(user_id=str(user.id))
                print(f"  -> Queued digest for {user.email}")

    try:
        return run_async(_run())
    except Exception as exc:
        print(f"[ERROR] generate_digests_for_all_users failed: {exc}")
        raise


# ─── Task 6: Refresh topics for one user ─────────────────────────────────────

@celery_app.task(
    bind=True,
    name="app.workers.tasks.refresh_topics_for_user",
    max_retries=2,
    default_retry_delay=60,
)
def refresh_topics_for_user(
    self,
    user_id: str,
    strategy: str = "auto",
    max_topics: int = 10,
):
    """
    Celery task: re-cluster topics for one user.
    Can be triggered manually via API or after ingestion completes.
    """
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.topic_service import refresh_topics

        print(f"[INFO] Celery: refreshing topics for user {user_id}")
        async with AsyncSessionLocal() as db:
            result = await refresh_topics(
                db=db,
                user_id=user_id,
                strategy=strategy,
                max_topics=max_topics,
            )
            print(f"[OK] Celery topics done: {result}")
            return result

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


# ─── Task 7: Process uploaded PDF ──────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="app.workers.tasks.process_pdf_task",
    max_retries=2,
    default_retry_delay=60,
)
def process_pdf_task(self, user_id: str, doc_id: str, file_path: str, job_id: str):
    """
    Celery task: process an uploaded PDF file.
    1. Extracts text
    2. Chunks & embeds
    3. Stores in ChromaDB and Postgres
    """
    async def _run():
        from app.database import AsyncSessionLocal
        from app.services.pdf_service import process_pdf_ingestion
        from app.utils.job_tracker import update_job
        import os

        await update_job(
            job_id,
            status="started",
            progress=10,
            message="Pingo started analyzing your PDF...",
        )

        async with AsyncSessionLocal() as db:
            try:
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"PDF file not found at {file_path}")

                await update_job(
                    job_id,
                    progress=30,
                    message="Extracting text from document...",
                )

                await process_pdf_ingestion(db, user_id, doc_id, file_path)

                await update_job(
                    job_id,
                    status="success",
                    progress=100,
                    message="PDF ingestion complete! You can now ask questions about it.",
                )

                # Also refresh topics to include the new document
                refresh_topics_for_user.delay(user_id=user_id)

            except Exception as e:
                await update_job(
                    job_id,
                    status="failed",
                    progress=0,
                    message="PDF processing failed",
                    error=str(e),
                )
                raise

    try:
        return run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)
