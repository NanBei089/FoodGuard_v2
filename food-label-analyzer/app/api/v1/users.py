from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.common import ApiResponse, success_response
from app.schemas.user import (
    ChangePasswordRequest,
    UpdateUserProfileRequest,
    UserProfileResponse,
)
from app.services.user_service import (
    change_user_password,
    deactivate_user,
    get_user_profile,
    update_user_profile,
)

router = APIRouter()


@router.get(
    "/me",
    response_model=ApiResponse[UserProfileResponse],
    summary="获取当前用户资料",
)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserProfileResponse]:
    payload = await get_user_profile(current_user)
    return success_response(payload)


@router.patch(
    "/me",
    response_model=ApiResponse[UserProfileResponse],
    summary="更新当前用户资料",
)
async def patch_me(
    request: UpdateUserProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserProfileResponse]:
    payload = await update_user_profile(
        current_user,
        display_name=request.display_name,
        avatar_url=request.avatar_url,
        db=db,
    )
    return success_response(payload)


@router.post(
    "/change-password",
    response_model=ApiResponse[None],
    summary="修改当前用户密码",
)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    await change_user_password(
        current_user,
        current_password=request.current_password,
        new_password=request.new_password,
        db=db,
    )
    return success_response(None)


@router.delete(
    "/me",
    response_model=ApiResponse[None],
    summary="注销当前账号",
)
async def delete_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    await deactivate_user(current_user, db)
    return success_response(None)


__all__ = ["router"]
