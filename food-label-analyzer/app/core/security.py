from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.errors import TokenExpiredError, TokenInvalidError

ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(
    user_id: str,
    token_type: str,
    expire_at: datetime,
    *,
    jti: str | None = None,
) -> str:
    settings = get_settings()
    payload = {
        "sub": user_id,
        "type": token_type,
        "exp": int(expire_at.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    if jti:
        payload["jti"] = jti
    return jwt.encode(
        payload,
        settings.APP_SECRET_KEY.get_secret_value(),
        algorithm=ALGORITHM,
    )


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    expire_at = datetime.now(timezone.utc) + settings.jwt_access_expire_timedelta
    return _create_token(
        user_id=user_id, token_type=ACCESS_TOKEN_TYPE, expire_at=expire_at
    )


def create_refresh_token(user_id: str, *, jti: str | None = None) -> str:
    settings = get_settings()
    expire_at = datetime.now(timezone.utc) + settings.jwt_refresh_expire_timedelta
    return _create_token(
        user_id=user_id,
        token_type=REFRESH_TOKEN_TYPE,
        expire_at=expire_at,
        jti=jti or uuid.uuid4().hex,
    )


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.APP_SECRET_KEY.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"verify_exp": False},
        )
    except JWTError as exc:
        raise TokenInvalidError() from exc

    exp = payload.get("exp")
    try:
        exp_timestamp = int(exp)
    except (TypeError, ValueError) as exc:
        raise TokenInvalidError() from exc

    if exp_timestamp <= int(datetime.now(timezone.utc).timestamp()):
        raise TokenExpiredError()
    return payload


__all__ = [
    "ACCESS_TOKEN_TYPE",
    "ALGORITHM",
    "REFRESH_TOKEN_TYPE",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "pwd_context",
    "verify_password",
]
