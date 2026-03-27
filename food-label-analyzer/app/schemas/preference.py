from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import BASE_MODEL_CONFIG

FocusGroup = Literal["adult", "child", "elder", "pregnant", "fitness"]
HealthCondition = Literal["diabetes", "hypertension", "hyperuricemia", "allergy"]


class _PreferenceSchema(BaseModel):
    model_config = BASE_MODEL_CONFIG


def _deduplicate_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


class UserPreferenceUpsertRequest(_PreferenceSchema):
    focus_groups: list[FocusGroup] = Field(default_factory=list, description="关注人群")
    health_conditions: list[HealthCondition] = Field(
        default_factory=list, description="健康状况"
    )
    allergies: list[str] = Field(default_factory=list, description="过敏源")

    @field_validator("allergies", mode="before")
    @classmethod
    def normalize_allergies(cls, value: list[str] | None) -> list[str]:
        if value is None:
            return []
        return _deduplicate_strings([str(item) for item in value])


class UserPreferenceResponse(_PreferenceSchema):
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
