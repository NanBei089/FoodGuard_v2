from __future__ import annotations

import importlib
import os

import structlog
from celery import Celery
from celery.signals import worker_init

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.workers import llm_worker, ocr_worker, rag_worker, yolo_worker

"""Celery 应用配置与 worker 预热逻辑。"""

settings = get_settings()
_IS_WINDOWS = os.name == "nt"

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
    worker_pool="solo" if _IS_WINDOWS else None,
    worker_concurrency=1 if _IS_WINDOWS else None,
    timezone="Asia/Shanghai",
    enable_utc=True,
)
importlib.import_module("app.tasks.analysis_task")


def _initialize_worker_resources() -> None:
    """初始化 worker 日志和外部资源。"""
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
    logger = structlog.get_logger(__name__)
    logger.info("celery_worker_initializing")

    try:
        yolo_worker.warmup()
    except Exception as exc:
        logger.warning("yolo_warmup_failed", error=str(exc))

    try:
        ocr_worker.warmup()
    except Exception as exc:
        logger.warning("ocr_warmup_failed", error=str(exc))

    try:
        rag_worker.warmup()
    except Exception as exc:
        logger.warning("rag_warmup_failed", error=str(exc))

    try:
        # LLM 只做配置校验，不在启动阶段发起真实分析请求，避免 worker 启动被外部模型阻塞。
        llm_worker.validate_configuration()
    except Exception as exc:
        logger.warning("llm_configuration_invalid", error=str(exc))

    logger.info("celery_worker_initialized")


@worker_init.connect
def on_worker_init(**kwargs) -> None:
    """Celery worker 启动信号回调。"""
    _initialize_worker_resources()


__all__ = ["celery_app", "on_worker_init"]
