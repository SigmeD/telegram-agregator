"""Celery application factory.

Start with::

    uv run celery -A worker.celery_app.app worker --loglevel=INFO
"""

from __future__ import annotations

from celery import Celery

from shared.config import get_settings


def create_app() -> Celery:
    """Build and configure the Celery app bound to Redis broker/backend."""

    settings = get_settings()
    celery_app = Celery(
        "tlg_worker",
        broker=settings.REDIS_URL,
        backend=settings.REDIS_URL,
        include=[
            "worker.tasks.filter_keywords",
            "worker.tasks.classify_llm",
            "worker.tasks.enrich_profile",
        ],
    )
    celery_app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_default_queue="default",
        task_routes={
            "worker.tasks.filter_keywords.*": {"queue": "filter"},
            "worker.tasks.classify_llm.*": {"queue": "llm"},
            "worker.tasks.enrich_profile.*": {"queue": "enrich"},
        },
        timezone="UTC",
        enable_utc=True,
    )
    return celery_app


app = create_app()


def main() -> None:
    """Console-script entry-point (delegates to Celery CLI)."""

    app.start()


if __name__ == "__main__":
    main()
