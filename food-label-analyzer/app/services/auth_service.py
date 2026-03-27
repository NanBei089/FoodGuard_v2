from __future__ import annotations

import asyncio
import random
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    CooldownError,
    EmailAlreadyExistsError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    InvalidVerifyCodeError,
    PasswordResetTokenInvalidError,
    PasswordTooWeakError,
    TokenInvalidError,
)
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    pwd_context,
    verify_password,
)
from app.models.email_verification import EmailVerification, VerificationType
from app.models.password_reset import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import TokenResponse, validate_password_strength
from app.services.email_service import send_reset_email as dispatch_reset_email
from app.services.email_service import send_verification_email

EMAIL_VERIFY_CODE_EXPIRE_SECONDS = 300
RESET_TOKEN_EXPIRE_SECONDS = 900
EMAIL_COOLDOWN_SECONDS = 60
_DUMMY_PASSWORD_HASH = pwd_context.hash("CodexDummyPassword123")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


async def _revoke_all_refresh_tokens_for_user(
    user_id: uuid.UUID, db: AsyncSession
) -> None:
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
    )
    now = datetime.now(timezone.utc)
    for token in result.scalars().all():
        token.revoked_at = now


async def _issue_token_response(user: User, db: AsyncSession) -> TokenResponse:
    settings = get_settings()
    refresh_jti = uuid.uuid4().hex
    refresh_token = create_refresh_token(str(user.id), jti=refresh_jti)
    refresh_record = RefreshToken(
        user_id=user.id,
        jti=refresh_jti,
        expires_at=datetime.now(timezone.utc) + settings.jwt_refresh_expire_timedelta,
    )
    db.add(refresh_record)
    await db.flush()
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _ensure_password_strength(password: str) -> None:
    try:
        validate_password_strength(password)
    except ValueError as exc:
        raise PasswordTooWeakError(str(exc)) from exc


async def send_register_code(email: str, db: AsyncSession, redis: Redis) -> int:
    normalized_email = _normalize_email(email)
    existing_user = await db.execute(
        select(User).where(User.email == normalized_email, User.is_verified.is_(True))
    )
    if existing_user.scalar_one_or_none() is not None:
        raise EmailAlreadyExistsError()

    cooldown_key = f"cooldown:register:{normalized_email}"
    if await redis.exists(cooldown_key):
        ttl = await redis.ttl(cooldown_key)
        raise CooldownError(max(ttl, 0))

    verification = EmailVerification(
        email=normalized_email,
        code=f"{random.randint(0, 999999):06d}",
        type=VerificationType.REGISTER,
        expired_at=datetime.now(timezone.utc)
        + timedelta(seconds=EMAIL_VERIFY_CODE_EXPIRE_SECONDS),
    )
    db.add(verification)
    await db.flush()
    await redis.set(cooldown_key, "1", ex=EMAIL_COOLDOWN_SECONDS)
    asyncio.create_task(send_verification_email(normalized_email, verification.code))
    return EMAIL_COOLDOWN_SECONDS


async def register_user(email: str, code: str, password: str, db: AsyncSession) -> None:
    normalized_email = _normalize_email(email)
    _ensure_password_strength(password)
    now = datetime.now(timezone.utc)

    verification_result = await db.execute(
        select(EmailVerification)
        .where(
            EmailVerification.email == normalized_email,
            EmailVerification.type == VerificationType.REGISTER,
            EmailVerification.is_used.is_(False),
            EmailVerification.expired_at > now,
        )
        .order_by(EmailVerification.created_at.desc())
        .limit(1)
    )
    verification = verification_result.scalar_one_or_none()
    if verification is None or verification.code != code:
        raise InvalidVerifyCodeError()

    existing_user = await db.execute(
        select(User).where(User.email == normalized_email, User.is_verified.is_(True))
    )
    if existing_user.scalar_one_or_none() is not None:
        raise EmailAlreadyExistsError()

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        is_verified=True,
        is_active=True,
    )
    verification.is_used = True
    db.add(user)

    try:
        await db.flush()
    except IntegrityError as exc:
        raise EmailAlreadyExistsError() from exc


async def login_user(email: str, password: str, db: AsyncSession) -> TokenResponse:
    normalized_email = _normalize_email(email)
    result = await db.execute(select(User).where(User.email == normalized_email))
    user = result.scalar_one_or_none()
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        raise InvalidCredentialsError()

    if not user.is_active:
        raise InvalidCredentialsError()
    if not user.is_verified:
        raise EmailNotVerifiedError()
    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()

    return await _issue_token_response(user, db)


async def logout_user(refresh_token: str, db: AsyncSession) -> None:
    payload = decode_token(refresh_token)
    if payload.get("type") != REFRESH_TOKEN_TYPE:
        raise TokenInvalidError()

    refresh_jti = payload.get("jti")
    if not refresh_jti:
        raise TokenInvalidError()

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.jti == str(refresh_jti))
    )
    token_record = result.scalar_one_or_none()
    if token_record is not None and token_record.revoked_at is None:
        token_record.revoked_at = datetime.now(timezone.utc)
        await db.flush()


async def refresh_tokens(refresh_token: str, db: AsyncSession) -> TokenResponse:
    payload = decode_token(refresh_token)
    if payload.get("type") != REFRESH_TOKEN_TYPE:
        raise TokenInvalidError()

    refresh_jti = payload.get("jti")
    if not refresh_jti:
        raise TokenInvalidError()

    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError) as exc:
        raise TokenInvalidError() from exc

    token_result = await db.execute(
        select(RefreshToken).where(RefreshToken.jti == str(refresh_jti))
    )
    token_record = token_result.scalar_one_or_none()
    if token_record is None or token_record.revoked_at is not None:
        raise TokenInvalidError()

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise TokenInvalidError()

    token_record.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    return await _issue_token_response(user, db)


async def send_reset_email(email: str, db: AsyncSession, redis: Redis) -> None:
    normalized_email = _normalize_email(email)
    cooldown_key = f"cooldown:reset:{normalized_email}"
    if await redis.exists(cooldown_key):
        ttl = await redis.ttl(cooldown_key)
        raise CooldownError(max(ttl, 0))

    result = await db.execute(
        select(User).where(User.email == normalized_email, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is not None:
        reset_token = PasswordResetToken(
            user_id=user.id,
            token=secrets.token_urlsafe(48),
            expired_at=datetime.now(timezone.utc)
            + timedelta(seconds=RESET_TOKEN_EXPIRE_SECONDS),
        )
        db.add(reset_token)
        await db.flush()
        asyncio.create_task(dispatch_reset_email(normalized_email, reset_token.token))

    await redis.set(cooldown_key, "1", ex=EMAIL_COOLDOWN_SECONDS)


async def reset_password(token: str, new_password: str, db: AsyncSession) -> None:
    _ensure_password_strength(new_password)
    now = datetime.now(timezone.utc)

    reset_result = await db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token == token,
            PasswordResetToken.is_used.is_(False),
            PasswordResetToken.expired_at > now,
        )
    )
    reset_token = reset_result.scalar_one_or_none()
    if reset_token is None:
        raise PasswordResetTokenInvalidError()

    user_result = await db.execute(select(User).where(User.id == reset_token.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise PasswordResetTokenInvalidError()

    user.password_hash = hash_password(new_password)
    reset_token.is_used = True
    await _revoke_all_refresh_tokens_for_user(user.id, db)
    await db.flush()


__all__ = [
    "login_user",
    "logout_user",
    "refresh_tokens",
    "register_user",
    "reset_password",
    "send_register_code",
    "send_reset_email",
    "_revoke_all_refresh_tokens_for_user",
]
