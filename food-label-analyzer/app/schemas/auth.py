from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import BASE_MODEL_CONFIG


class _AuthSchema(BaseModel):
    model_config = BASE_MODEL_CONFIG


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def validate_password_strength(password: str) -> str:
    has_upper = re.search(r"[A-Z]", password)
    has_lower = re.search(r"[a-z]", password)
    has_digit = re.search(r"\d", password)
    if not all((has_upper, has_lower, has_digit)):
        raise ValueError(
            "Password must contain uppercase, lowercase, and digit characters"
        )
    return password


class SendCodeRequest(_AuthSchema):
    email: EmailStr = Field(description="Email address", examples=["user@example.com"])

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class RegisterRequest(_AuthSchema):
    email: EmailStr = Field(description="Email address", examples=["user@example.com"])
    code: str = Field(
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="Six-digit verification code",
        examples=["123456"],
    )
    password: str = Field(
        min_length=8,
        max_length=32,
        description="New password",
        examples=["StrongPass123"],
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_strength(value)


class LoginRequest(_AuthSchema):
    email: EmailStr = Field(description="Email address", examples=["user@example.com"])
    password: str = Field(
        min_length=1, description="Password", examples=["StrongPass123"]
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class RefreshTokenRequest(_AuthSchema):
    refresh_token: str = Field(
        min_length=1, description="Refresh token", examples=["eyJhbGciOi..."]
    )


class LogoutRequest(_AuthSchema):
    refresh_token: str = Field(
        min_length=1, description="Refresh token to revoke", examples=["eyJhbGciOi..."]
    )


class ForgotPasswordRequest(_AuthSchema):
    email: EmailStr = Field(description="Email address", examples=["user@example.com"])

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)


class ResetPasswordRequest(_AuthSchema):
    token: str = Field(
        min_length=1, description="Password reset token", examples=["reset-token-value"]
    )
    new_password: str = Field(
        min_length=8,
        max_length=32,
        description="New password",
        examples=["NewStrongPass123"],
    )

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_strength(value)


class TokenResponse(_AuthSchema):
    access_token: str = Field(description="Access token", examples=["eyJhbGciOi..."])
    refresh_token: str = Field(description="Refresh token", examples=["eyJhbGciOi..."])
    token_type: str = Field(
        default="Bearer", description="Token type", examples=["Bearer"]
    )
    expires_in: int = Field(description="Access token ttl in seconds", examples=[1800])


class CooldownResponse(_AuthSchema):
    cooldown_seconds: int = Field(
        ge=0,
        description="Cooldown duration in seconds before the next request",
        examples=[60],
    )


__all__ = [
    "CooldownResponse",
    "ForgotPasswordRequest",
    "LoginRequest",
    "LogoutRequest",
    "RefreshTokenRequest",
    "RegisterRequest",
    "ResetPasswordRequest",
    "SendCodeRequest",
    "TokenResponse",
    "validate_password_strength",
]
