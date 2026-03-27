from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_serializer

T = TypeVar("T")


def serialize_datetime_to_z(value: datetime) -> str:
    normalized = (
        value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    )
    normalized = normalized.astimezone(timezone.utc)
    return normalized.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _serialize_datetime(value: datetime) -> str:
    return serialize_datetime_to_z(value)


BASE_MODEL_CONFIG = ConfigDict(
    from_attributes=True,
)


class ApiResponse(BaseModel, Generic[T]):
    model_config = BASE_MODEL_CONFIG

    code: int = Field(default=0, description="业务状态码，0 表示成功", examples=[0])
    message: str = Field(default="ok", description="响应消息", examples=["ok"])
    data: T | None = Field(default=None, description="响应数据")

    @field_serializer("data")
    def serialize_data(self, value: T | None) -> T | str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return _serialize_datetime(value)
        return value


def success_response(data: T | None, message: str = "ok") -> ApiResponse[T]:
    return ApiResponse[T](message=message, data=data)


class PageRequest(BaseModel):
    model_config = BASE_MODEL_CONFIG

    page: int = Field(default=1, ge=1, description="页码，从 1 开始", examples=[1])
    page_size: int = Field(
        default=10,
        ge=1,
        le=50,
        description="每页条数，最大 50",
        examples=[10],
    )


class PageResponse(BaseModel, Generic[T]):
    model_config = BASE_MODEL_CONFIG

    items: list[T] = Field(description="当前页数据列表")
    total: int = Field(description="总记录数", examples=[0, 12])
    page: int = Field(description="当前页码", examples=[1])
    page_size: int = Field(description="每页条数", examples=[10])

    @computed_field
    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return math.ceil(self.total / self.page_size)


__all__ = [
    "ApiResponse",
    "BASE_MODEL_CONFIG",
    "PageRequest",
    "PageResponse",
    "serialize_datetime_to_z",
    "success_response",
]
