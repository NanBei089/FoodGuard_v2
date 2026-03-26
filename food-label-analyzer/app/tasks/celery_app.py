from __future__ import annotations

import structlog
from celery import Celery
from celery.signals import worker_init

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.workers import llm_worker, ocr_worker, rag_worker, yolo_worker


settings = get_settings()

celery_app = Celery("food_label_analyzer")
celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    task_default_queue="analysis",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=270,
    task_time_limit=300,
    timezone="Asia/Shanghai",
    enable_utc=True,
)
celery_app.autodiscover_tasks(["app.tasks"])


def _initialize_worker_resources() -> None:
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
    logger = structlog.get_logger(__name__)
    logger.info("celery_worker_initializing")

    try:
        yolo_worker.warmup()
    except Exception as exc:
        logger.critical("yolo_warmup_failed", error=str(exc))
        raise

    try:
        ocr_worker.warmup()
    except Exception as exc:
        logger.warning("ocr_warmup_failed", error=str(exc))

    try:
        rag_worker.warmup()
    except Exception as exc:
        logger.warning("rag_warmup_failed", error=str(exc))

    try:
        llm_worker.validate_configuration()
    except Exception as exc:
        logger.warning("llm_configuration_invalid", error=str(exc))

    logger.info("celery_worker_initialized")


@worker_init.connect
def on_worker_init(**kwargs) -> None:
    _initialize_worker_resources()


__all__ = ["celery_app", "on_worker_init"]
