from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidCredentialsError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserProfileResponse
from app.services.auth_service import _revoke_all_refresh_tokens_for_user


def _build_user_profile(user: User) -> UserProfileResponse:
    return UserProfileResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        is_verified=user.is_verified,
        created_at=user.created_at,
    )


async def get_user_profile(user: User) -> UserProfileResponse:
    return _build_user_profile(user)


async def update_user_profile(
    user: User,
    *,
    display_name: str | None,
    avatar_url: str | None,
    db: AsyncSession,
) -> UserProfileResponse:
    if display_name is not None:
        user.display_name = display_name
    if avatar_url is not None:
        user.avatar_url = avatar_url
    await db.flush()
    return _build_user_profile(user)


async def change_user_password(
    user: User,
    *,
    current_password: str,
    new_password: str,
    db: AsyncSession,
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError("当前密码错误")
    user.password_hash = hash_password(new_password)
    await _revoke_all_refresh_tokens_for_user(user.id, db)
    await db.flush()


async def deactivate_user(user: User, db: AsyncSession) -> None:
    user.is_active = False
    user.deleted_at = datetime.now(timezone.utc)
    await _revoke_all_refresh_tokens_for_user(user.id, db)
    await db.flush()


__all__ = [
    "change_user_password",
    "deactivate_user",
    "get_user_profile",
    "update_user_profile",
]
