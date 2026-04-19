from __future__ import annotations

import io
import uuid
from typing import Literal, cast

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import (
    FileTooLargeError,
    InvalidFileTypeError,
    TaskNotFoundError,
    TooManyConcurrentTasksError,
)
from app.models.analysis_task import AnalysisTask, TaskStatus
from app.models.report import Report
from app.schemas.analysis import (
    STATUS_MESSAGES,
    TaskStatusResponse,
    sanitize_error_message,
    to_external_task_status,
)

"""分析任务服务，负责上传校验、任务创建与状态投影。"""


def _detect_image_type(data: bytes) -> str | None:
    """基于文件魔数识别图片类型，避免只依赖扩展名。"""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"\x89PNG":
        return "image/png"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def validate_file(file: UploadFile) -> tuple[bytes, str]:
    """校验上传图片的完整性、大小与 MIME 类型。

    Params:
        file: FastAPI 上传文件对象。

    Returns:
        tuple[bytes, str]: 文件字节流与识别出的 content type。
    """
    settings = get_settings()
    if file is None or not file.filename:
        raise InvalidFileTypeError("上传文件缺失")

    file_bytes = await file.read()
    if not file_bytes:
        raise InvalidFileTypeError("上传文件为空")
    if len(file_bytes) > settings.max_upload_size_bytes:
        raise FileTooLargeError(f"上传文件超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制")

    content_type = _detect_image_type(file_bytes)
    if content_type is None or content_type not in settings.allowed_image_types_list:
        raise InvalidFileTypeError("仅支持 JPG、PNG 和 WEBP 图片")

    try:
        # 额外做一次 Pillow 校验，尽早拦住损坏图片，避免后续 OCR/YOLO 才暴露问题。
        with Image.open(io.BytesIO(file_bytes)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidFileTypeError("上传图片已损坏") from exc

    return file_bytes, content_type


async def check_concurrent_limit(user_id: uuid.UUID, db: AsyncSession) -> None:
    """校验用户并发分析任务数是否超限。"""
    settings = get_settings()
    result = await db.execute(
        select(func.count())
        .select_from(AnalysisTask)
        .where(
            AnalysisTask.user_id == user_id,
            AnalysisTask.status.in_((TaskStatus.PENDING, TaskStatus.PROCESSING)),
        )
    )
    count = int(result.scalar_one())
    if count >= settings.USER_MAX_CONCURRENT_TASKS:
        raise TooManyConcurrentTasksError()


async def create_task(
    user_id: uuid.UUID,
    image_key: str,
    image_url: str,
    db: AsyncSession,
) -> AnalysisTask:
    """创建待处理分析任务记录。"""
    task = AnalysisTask(
        user_id=user_id,
        image_key=image_key,
        image_url=image_url,
        status=TaskStatus.PENDING,
    )
    db.add(task)
    await db.flush()
    return task


async def update_celery_task_id(
    task_id: uuid.UUID, celery_task_id: str, db: AsyncSession
) -> None:
    """回填 Celery 任务 ID，便于排障与追踪。"""
    task = await db.get(AnalysisTask, task_id)
    if task is not None:
        task.celery_task_id = celery_task_id
        await db.flush()


async def get_task_with_permission(
    task_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> AnalysisTask:
    """按用户权限范围加载任务，防止越权访问。"""
    result = await db.execute(
        select(AnalysisTask)
        .options(selectinload(AnalysisTask.report))
        .where(AnalysisTask.id == task_id, AnalysisTask.user_id == user_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise TaskNotFoundError()
    return task


async def get_task_status_payload(
    task: AnalysisTask, db: AsyncSession
) -> TaskStatusResponse:
    """把内部任务状态映射成对前端稳定的响应结构。"""
    report = task.report
    if report is None and task.status == TaskStatus.COMPLETED:
        # Worker 完成和 ORM 关系刷新可能存在短暂竞态，这里补查一次确保状态可见。
        result = await db.execute(select(Report).where(Report.task_id == task.id))
        report = result.scalar_one_or_none()
    external_status = cast(
        "Literal['queued', 'processing', 'completed', 'failed']",
        to_external_task_status(task.status.value),
    )
    nutrition_parse_source = cast(
        "Literal['table_recognition', 'ocr_text', 'llm_fallback', 'empty', 'failed'] | None",
        report.nutrition_parse_source if report is not None else None,
    )

    return TaskStatusResponse(
        task_id=task.id,
        status=external_status,
        progress_message=STATUS_MESSAGES.get(
            external_status,
            "系统正在处理中",
        ),
        created_at=task.created_at,
        completed_at=task.completed_at,
        report_id=report.id if report is not None else None,
        error_message=sanitize_error_message(task.error_message),
        nutrition_parse_source=nutrition_parse_source,
    )


__all__ = [
    "check_concurrent_limit",
    "create_task",
    "get_task_status_payload",
    "get_task_with_permission",
    "update_celery_task_id",
    "validate_file",
]
