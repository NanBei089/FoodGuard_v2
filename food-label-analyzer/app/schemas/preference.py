from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import BASE_MODEL_CONFIG

"""用户健康偏好 schema。"""

FocusGroup = Literal["adult", "child", "elder", "pregnant", "fitness"]
HealthCondition = Literal["diabetes", "hypertension", "hyperuricemia", "allergy"]


class _PreferenceSchema(BaseModel):
    """偏好 schema 的公共基类。"""

    model_config = BASE_MODEL_CONFIG


def _deduplicate_strings(values: list[str]) -> list[str]:
    """去除空字符串和重复项，同时保留原有顺序。"""
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


class UserPreferenceUpsertRequest(_PreferenceSchema):
    """保存用户偏好请求。"""

    focus_groups: list[FocusGroup] = Field(default_factory=list, description="关注人群")
    health_conditions: list[HealthCondition] = Field(
        default_factory=list, description="健康状况"
    )
    allergies: list[str] = Field(default_factory=list, description="过敏源")

    @field_validator("allergies", mode="before")
    @classmethod
    def normalize_allergies(cls, value: list[str] | None) -> list[str]:
        """规范化过敏原列表。"""
        if value is None:
            return []
        return _deduplicate_strings([str(item) for item in value])


class UserPreferenceResponse(_PreferenceSchema):
    """用户偏好响应。"""

    focus_groups: list[FocusGroup] = Field(default_factory=list, description="关注人群")
    health_conditions: list[HealthCondition] = Field(
        default_factory=list, description="健康状况"
    )
    allergies: list[str] = Field(default_factory=list, description="过敏源")
    updated_at: datetime = Field(
        description="偏好更新时间", examples=["2026-03-26T00:00:00Z"]
    )


__all__ = [
    "HealthCondition",
    "FocusGroup",
    "UserPreferenceResponse",
    "UserPreferenceUpsertRequest",
]
