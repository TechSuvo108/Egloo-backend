# app/workers/celery_app.py

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "egloo",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Performance & Reliability
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="celery",

    # Retry failed tasks up to 3 times with 60s delay
    task_max_retries=3,
    task_default_retry_delay=60,

    # Beat schedule — runs periodic tasks automatically
    beat_schedule={

        # Auto-sync all sources every 15 minutes
        "auto-sync-all-sources": {
            "task": "app.workers.tasks.auto_sync_all_users",
            "schedule": crontab(minute="*/15"),
        },

        # Generate daily digest at 7 AM UTC every day
        "generate-daily-digests": {
            "task": "app.workers.tasks.generate_digests_for_all_users",
            "schedule": crontab(hour=7, minute=0),
        },

        # Proactive brain refresh at 6 AM UTC (before digest)
        "daily-brain-refresh": {
            "task": "app.workers.tasks.daily_brain_refresh",
            "schedule": crontab(hour=6, minute=0),
        },

        # Heartbeat every minute
        "scheduler-heartbeat": {
            "task": "app.workers.tasks.scheduler_heartbeat",
            "schedule": crontab(minute="*"),
        },
    },
)
