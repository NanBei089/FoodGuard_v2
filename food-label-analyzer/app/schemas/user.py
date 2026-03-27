from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import validate_password_strength
from app.schemas.common import BASE_MODEL_CONFIG


class _UserSchema(BaseModel):
    model_config = BASE_MODEL_CONFIG


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class UserProfileResponse(_UserSchema):
    user_id: UUID = Field(description="当前用户 ID")
    email: str = Field(description="当前用户邮箱", examples=["user@example.com"])
    display_name: str | None = Field(
        default=None, description="显示名称", examples=["李雷"]
    )
    avatar_url: str | None = Field(
        default=None,
        description="头像地址",
        examples=["https://example.com/avatar.png"],
    )
    is_verified: bool = Field(description="邮箱是否已验证", examples=[True])
    created_at: datetime = Field(
        description="账号创建时间", examples=["2026-03-26T00:00:00Z"]
    )


class UpdateUserProfileRequest(_UserSchema):
    display_name: str | None = Field(
        default=None, min_length=1, max_length=64, description="显示名称"
    )
    avatar_url: str | None = Field(
        default=None, max_length=1024, description="头像地址"
    )

    @field_validator("display_name", "avatar_url", mode="before")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return _normalize_optional_text(value)


class ChangePasswordRequest(_UserSchema):
    current_password: str = Field(
        min_length=1, description="当前密码", examples=["OldPass123"]
    )
    new_password: str = Field(
        min_length=8, max_length=32, description="新密码", examples=["NewStrongPass123"]
    )

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_strength(value)


__all__ = [
    "ChangePasswordRequest",
    "UpdateUserProfileRequest",
    "UserProfileResponse",
]
