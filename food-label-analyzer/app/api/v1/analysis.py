from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ExternalServiceException
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.analysis import TaskCreateResponse, TaskStatusResponse
from app.schemas.common import ApiResponse, success_response
from app.services.storage_service import get_storage_service
from app.services.task_service import (
    check_concurrent_limit,
    create_task,
    get_task_status_payload,
    get_task_with_permission,
    update_celery_task_id,
    validate_file,
)
from app.tasks.celery_app import celery_app


router = APIRouter()


@router.post(
    "/upload",
    response_model=ApiResponse[TaskCreateResponse],
    summary="上传待分析图片",
    description="上传食品标签图片，创建分析任务并返回任务基础信息。",
    responses={
        200: {"description": "上传成功并已创建任务"},
        400: {"description": "文件校验失败"},
        401: {"description": "未认证"},
        429: {"description": "并发任务超限"},
        503: {"description": "任务入队或外部服务失败"},
    },
)
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskCreateResponse]:
    storage_service = get_storage_service()
    file_bytes, content_type = await validate_file(file)
    await check_concurrent_limit(current_user.id, db)
    image_key, image_url = await storage_service.upload_image(
        file_bytes,
        str(current_user.id),
        content_type,
    )
    task = await create_task(current_user.id, image_key, image_url, db)

    try:
        celery_result = celery_app.send_task(
            "analysis.process_image",
            args=[str(task.id), image_key, str(current_user.id)],
            queue="analysis",
        )
        await update_celery_task_id(task.id, celery_result.id, db)
    except Exception as exc:
        try:
            await storage_service.delete_image(image_key)
        except Exception:
            pass
        raise ExternalServiceException("分析任务入队失败") from exc

    return success_response(
        TaskCreateResponse(
            task_id=task.id,
            status=task.status.value,
            created_at=task.created_at,
        ),
        message="图片上传成功",
    )


@router.get(
    "/tasks/{task_id}",
    response_model=ApiResponse[TaskStatusResponse],
    summary="查询任务状态",
    description="根据任务 ID 查询当前分析任务状态、报告 ID 和可见错误信息。",
    responses={
        200: {"description": "查询成功"},
        401: {"description": "未认证"},
        404: {"description": "任务不存在"},
    },
)
async def get_task_status(
    task_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TaskStatusResponse]:
    task = await get_task_with_permission(task_id, current_user.id, db)
    payload = await get_task_status_payload(task, db)
    return success_response(payload)


__all__ = ["router"]
