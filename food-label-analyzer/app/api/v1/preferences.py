from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse, success_response
from app.schemas.preference import UserPreferenceResponse, UserPreferenceUpsertRequest
from app.services.preference_service import (
    get_user_preferences,
    upsert_user_preferences,
)

router = APIRouter()


@router.get(
    "/me",
    response_model=ApiResponse[UserPreferenceResponse],
    summary="获取当前用户偏好",
)
async def get_me_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserPreferenceResponse]:
    payload = await get_user_preferences(current_user, db)
    return success_response(payload)


@router.put(
    "/me",
    response_model=ApiResponse[UserPreferenceResponse],
    summary="保存当前用户偏好",
)
async def put_me_preferences(
    request: UserPreferenceUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserPreferenceResponse]:
    payload = await upsert_user_preferences(
        current_user,
        focus_groups=request.focus_groups,
        health_conditions=request.health_conditions,
        allergies=request.allergies,
        db=db,
    )
    return success_response(payload)


__all__ = ["router"]
