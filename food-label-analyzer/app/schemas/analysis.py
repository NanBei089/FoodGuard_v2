from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import BASE_MODEL_CONFIG

STATUS_MESSAGES = {
    "queued": "任务排队中，请稍候...",
    "processing": "正在分析食品标签...",
    "completed": "分析完成",
    "failed": "分析失败，请重新上传图片",
}

INTERNAL_TO_EXTERNAL_STATUS = {
    "pending": "queued",
    "processing": "processing",
    "completed": "completed",
    "failed": "failed",
}

NutritionParseSourceLiteral = Literal[
    "table_recognition", "ocr_text", "llm_fallback", "empty", "failed"
]


def to_external_task_status(internal_status: str) -> str:
    return INTERNAL_TO_EXTERNAL_STATUS.get(internal_status, internal_status)


def sanitize_error_message(internal_error: str | None) -> str | None:
    if internal_error is None:
        return None

    normalized = internal_error.lower()
    if (
        "超时" in internal_error
        or "timeout" in normalized
        or "softtimelimit" in normalized
    ):
        return "任务处理超时，请重新上传"
    if "重试" in internal_error or "retry" in normalized:
        return "服务暂时繁忙，请稍后重试"
    if "ocr" in normalized or "table" in normalized:
        return "OCR 子系统暂时不可用，请稍后重试"
    return "分析失败，请重新上传图片"


class _AnalysisSchema(BaseModel):
    model_config = BASE_MODEL_CONFIG


class TaskCreateResponse(_AnalysisSchema):
    task_id: UUID = Field(description="任务 ID")
    status: Literal["queued"] = Field(
        default="queued", description="对外任务状态", examples=["queued"]
    )
    created_at: datetime = Field(
        description="任务创建时间", examples=["2026-03-25T12:30:00Z"]
    )


class TaskStatusResponse(_AnalysisSchema):
    task_id: UUID = Field(description="任务 ID")
    status: Literal["queued", "processing", "completed", "failed"] = Field(
        description="对外任务状态",
        examples=["processing"],
    )
    progress_message: str = Field(description="任务进度描述")
    created_at: datetime = Field(
        description="任务创建时间", examples=["2026-03-25T12:30:00Z"]
    )
    completed_at: datetime | None = Field(
        default=None,
        description="任务完成时间",
        examples=["2026-03-25T12:32:00Z"],
    )
    report_id: UUID | None = Field(default=None, description="关联报告 ID")
    error_message: str | None = Field(default=None, description="脱敏后的错误信息")
    nutrition_parse_source: NutritionParseSourceLiteral | None = Field(
        default=None,
        description="营养解析来源",
        examples=["table_recognition", "ocr_text"],
    )


__all__ = [
    "STATUS_MESSAGES",
    "TaskCreateResponse",
    "TaskStatusResponse",
    "sanitize_error_message",
    "to_external_task_status",
]
