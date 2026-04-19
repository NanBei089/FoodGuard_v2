from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_preference import UserPreference
from app.schemas.preference import UserPreferenceResponse

"""用户饮食偏好领域服务。"""


def _derive_health_conditions(
    health_conditions: Sequence[str], allergies: Sequence[str]
) -> list[str]:
    """根据过敏原列表补全 `allergy` 健康条件标记。"""
    normalized = [item for item in health_conditions if item]
    if allergies and "allergy" not in normalized:
        normalized.append("allergy")
    return normalized


def _build_preference_response(
    *,
    focus_groups: Sequence[str],
    health_conditions: Sequence[str],
    allergies: Sequence[str],
    updated_at,
) -> UserPreferenceResponse:
    """构造统一的偏好响应模型。"""
    return UserPreferenceResponse(
        focus_groups=list(focus_groups),
        health_conditions=list(health_conditions),
        allergies=list(allergies),
        updated_at=updated_at,
    )


async def get_user_preferences(user: User, db: AsyncSession) -> UserPreferenceResponse:
    """读取用户偏好；若不存在则返回空偏好。"""
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )
    preference = result.scalar_one_or_none()
    if preference is None:
        return _build_preference_response(
            focus_groups=[],
            health_conditions=[],
            allergies=[],
            updated_at=user.updated_at,
        )

    return _build_preference_response(
        focus_groups=list(preference.focus_groups or []),
        health_conditions=list(preference.health_conditions or []),
        allergies=list(preference.allergies or []),
        updated_at=preference.updated_at,
    )


async def upsert_user_preferences(
    user: User,
    *,
    focus_groups: Sequence[str],
    health_conditions: Sequence[str],
    allergies: Sequence[str],
    db: AsyncSession,
) -> UserPreferenceResponse:
    """创建或更新用户偏好配置。"""
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )
    preference = result.scalar_one_or_none()
    derived_health_conditions = _derive_health_conditions(health_conditions, allergies)
    # 过敏原是前端的细粒度输入，但后续分析链路只依赖统一的 health condition 标记。
    focus_groups_list = list(focus_groups)
    allergies_list = list(allergies)

    if preference is None:
        preference = UserPreference(
            user_id=user.id,
            focus_groups=focus_groups_list,
            health_conditions=derived_health_conditions,
            allergies=allergies_list,
        )
        db.add(preference)
        await db.flush()
        return _build_preference_response(
            focus_groups=focus_groups_list,
            health_conditions=derived_health_conditions,
            allergies=allergies_list,
            updated_at=preference.updated_at,
        )

    preference.focus_groups = focus_groups_list
    preference.health_conditions = derived_health_conditions
    preference.allergies = allergies_list
    preference.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return _build_preference_response(
        focus_groups=focus_groups_list,
        health_conditions=derived_health_conditions,
        allergies=allergies_list,
        updated_at=preference.updated_at,
    )


__all__ = ["get_user_preferences", "upsert_user_preferences"]
