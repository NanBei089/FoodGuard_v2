from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import BASE_MODEL_CONFIG


STATUS_MESSAGES = {
    "pending": "任务已创建，等待分析",
    "processing": "系统正在分析上传图片",
    "completed": "分析已完成",
    "failed": "分析失败",
}


def sanitize_error_message(internal_error: str | None) -> str | None:
    if not internal_error:
        return None

    normalized = internal_error.lower()
    if "timeout" in normalized or "softtimelimit" in normalized:
        return "分析超时，请稍后重试。"
    if "storage" in normalized or "minio" in normalized:
        return "存储服务暂时不可用。"
    if "ocr" in normalized or "table" in normalized:
        return "OCR 服务暂时不可用。"
    if "llm" in normalized or "deepseek" in normalized:
        return "大模型服务暂时不可用。"
    if "embedding" in normalized or "chroma" in normalized or "rag" in normalized:
        return "知识检索服务暂时不可用。"
    return "分析失败，请重新上传图片后再试。"


class _AnalysisSchema(BaseModel):
    model_config = BASE_MODEL_CONFIG


class TaskCreateResponse(_AnalysisSchema):
    task_id: UUID = Field(description="Task identifier")
    status: str = Field(description="Current task status", examples=["pending"])
    created_at: datetime = Field(description="Task creation time", examples=["2026-03-25T12:30:00Z"])


class TaskStatusResponse(_AnalysisSchema):
    task_id: UUID = Field(description="Task identifier")
    status: str = Field(description="Current task status", examples=["processing"])
    progress_message: str = Field(description="Human-readable task progress message")
    created_at: datetime = Field(description="Task creation time", examples=["2026-03-25T12:30:00Z"])
    completed_at: datetime | None = Field(
        default=None,
        description="Task completion time",
        examples=["2026-03-25T12:32:00Z"],
    )
    report_id: UUID | None = Field(default=None, description="Generated report identifier")
    error_message: str | None = Field(default=None, description="Sanitized error message")
    nutrition_parse_source: str | None = Field(
        default=None,
        description="Nutrition parsing source when the report is available",
        examples=["table_recognition", "ocr_text"],
    )


__all__ = [
    "STATUS_MESSAGES",
    "TaskCreateResponse",
    "TaskStatusResponse",
    "sanitize_error_message",
]
