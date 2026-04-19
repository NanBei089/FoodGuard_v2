from __future__ import annotations

import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import TokenExpiredError, TokenInvalidError
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.db.session import get_db
from app.models.user import User

"""FastAPI 依赖项定义，例如当前登录用户解析。"""

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 access token 解析并加载当前用户。

    Params:
        token: OAuth2 Bearer token。
        db: 当前请求使用的数据库会话。

    Returns:
        User: 已校验状态且仍然激活的用户对象。
    """
    try:
        payload = decode_token(token)
    except (TokenExpiredError, TokenInvalidError):
        raise

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise TokenInvalidError()

    user_id = payload.get("sub")
    if not user_id:
        raise TokenInvalidError()

    try:
        parsed_user_id = uuid.UUID(str(user_id))
    except ValueError as exc:
        raise TokenInvalidError() from exc

    result = await db.execute(select(User).where(User.id == parsed_user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise TokenInvalidError()

    return user


__all__ = ["get_current_user", "oauth2_scheme"]
