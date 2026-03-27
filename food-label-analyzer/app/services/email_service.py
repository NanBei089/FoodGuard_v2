from __future__ import annotations

import structlog

from app.core.config import get_settings
from app.core.email import get_email_service

logger = structlog.get_logger(__name__)


async def send_verification_email(email: str, code: str) -> None:
    try:
        await get_email_service().send_verification_code(email, code)
    except Exception as exc:
        logger.warning(
            "verification_email_dispatch_failed",
            email=email,
            exception_type=exc.__class__.__name__,
            exception_message=str(exc),
        )


async def send_reset_email(email: str, token: str) -> None:
    reset_link = f"{get_settings().FRONTEND_URL}/reset-password?token={token}"
    try:
        await get_email_service().send_password_reset(email, reset_link)
    except Exception as exc:
        logger.warning(
            "password_reset_email_dispatch_failed",
            email=email,
            exception_type=exc.__class__.__name__,
            exception_message=str(exc),
        )


__all__ = ["send_reset_email", "send_verification_email"]
