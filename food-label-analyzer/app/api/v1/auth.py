from __future__ import annotations

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import get_redis
from app.db.session import get_db
from app.schemas.auth import (
    CooldownResponse,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SendCodeRequest,
    TokenResponse,
)
from app.schemas.common import ApiResponse, success_response
from app.services.auth_service import (
    login_user,
    logout_user,
    refresh_tokens,
    register_user,
    reset_password,
    send_register_code,
    send_reset_email,
)

router = APIRouter()


@router.post(
    "/register/send-code",
    response_model=ApiResponse[CooldownResponse],
    summary="发送注册验证码",
    description="向待注册邮箱发送六位数字验证码，并返回当前冷却时间。",
    responses={
        200: {"description": "验证码发送成功"},
        409: {"description": "邮箱已注册"},
        429: {"description": "请求过于频繁"},
        503: {"description": "外部服务暂时不可用"},
    },
)
async def register_send_code(
    request: SendCodeRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ApiResponse[CooldownResponse]:
    cooldown_seconds = await send_register_code(request.email, db, redis)
    return success_response(
        CooldownResponse(cooldown_seconds=cooldown_seconds),
        message="验证码已发送",
    )


@router.post(
    "/register",
    response_model=ApiResponse[None],
    summary="注册账号",
    description="使用邮箱、验证码和密码完成注册。",
    responses={
        200: {"description": "注册成功"},
        400: {"description": "验证码或密码不合法"},
        409: {"description": "邮箱已注册"},
    },
)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    await register_user(request.email, request.code, request.password, db)
    return success_response(None, message="注册成功")


@router.post(
    "/login",
    response_model=ApiResponse[TokenResponse],
    summary="用户登录",
    description="使用邮箱和密码登录，返回访问令牌和刷新令牌。",
    responses={
        200: {"description": "登录成功"},
        401: {"description": "邮箱或密码错误"},
        403: {"description": "邮箱未验证"},
    },
)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TokenResponse]:
    tokens = await login_user(request.email, request.password, db)
    return success_response(tokens)


@router.post(
    "/refresh",
    response_model=ApiResponse[TokenResponse],
    summary="刷新令牌",
    description="使用刷新令牌换取新的访问令牌和刷新令牌。",
    responses={
        200: {"description": "刷新成功"},
        401: {"description": "刷新令牌无效"},
    },
)
async def refresh(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TokenResponse]:
    tokens = await refresh_tokens(request.refresh_token, db)
    return success_response(tokens)


@router.post(
    "/logout",
    response_model=ApiResponse[None],
    summary="用户登出",
    description="将当前 refresh token 标记为失效，重复登出保持幂等。",
    responses={
        200: {"description": "登出成功"},
        401: {"description": "刷新令牌无效"},
    },
)
async def logout(
    request: LogoutRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    await logout_user(request.refresh_token, db)
    return success_response(None)


@router.post(
    "/forgot-password",
    response_model=ApiResponse[None],
    summary="发送重置密码邮件",
    description="如果账号存在，则发送重置密码邮件；接口不会暴露邮箱是否存在。",
    responses={
        200: {"description": "请求已受理"},
        429: {"description": "请求过于频繁"},
        503: {"description": "外部服务暂时不可用"},
    },
)
async def forgot_password(
    request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ApiResponse[None]:
    await send_reset_email(request.email, db, redis)
    return success_response(None, message="如果账号存在，重置邮件已发送")


@router.post(
    "/reset-password",
    response_model=ApiResponse[None],
    summary="重置密码",
    description="使用密码重置令牌和新密码完成密码重置。",
    responses={
        200: {"description": "密码重置成功"},
        400: {"description": "重置链接无效或已过期"},
    },
)
async def reset_password_endpoint(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    await reset_password(request.token, request.new_password, db)
    return success_response(None, message="密码已重置")


__all__ = ["router"]
