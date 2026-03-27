from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from app.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)


class EmailService:
    def __init__(self, settings: Settings) -> None:
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD.get_secret_value()
        self.from_name = settings.SMTP_FROM_NAME
        self.from_email = settings.SMTP_FROM_EMAIL
        self.use_tls = settings.SMTP_USE_TLS

    async def send_verification_code(self, email: str, code: str) -> None:
        subject = "Your Food Label Analyzer verification code"
        html_body = (
            "<p>Your verification code is:</p>"
            f"<p style='font-size:24px;font-weight:bold'>{code}</p>"
            "<p>The code will expire in 5 minutes.</p>"
        )
        await self._send(email, subject, html_body)

    async def send_password_reset(self, email: str, reset_link: str) -> None:
        subject = "Reset your Food Label Analyzer password"
        html_body = (
            "<p>We received a password reset request for your account.</p>"
            f"<p><a href='{reset_link}'>Reset password</a></p>"
            "<p>The link will expire in 15 minutes.</p>"
        )
        await self._send(email, subject, html_body)

    async def _send(self, to: str, subject: str, html_body: str) -> None:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{self.from_name} <{self.from_email}>"
        message["To"] = to
        message.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_fixed(2),
                retry=retry_if_exception_type(
                    (
                        aiosmtplib.SMTPException,
                        ConnectionError,
                        OSError,
                    )
                ),
                reraise=True,
            ):
                with attempt:
                    await aiosmtplib.send(
                        message,
                        hostname=self.host,
                        port=self.port,
                        username=self.username,
                        password=self.password,
                        start_tls=self.use_tls and self.port != 465,
                        use_tls=self.use_tls and self.port == 465,
                    )
        except Exception as exc:
            logger.warning(
                "email_send_failed",
                to=to,
                subject=subject,
                exception_type=exc.__class__.__name__,
                exception_message=str(exc),
            )
            return

        logger.info("email_sent", to=to, subject=subject)


_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    global _email_service
    if _email_service is None:
        _email_service = EmailService(get_settings())
    return _email_service


__all__ = ["EmailService", "get_email_service"]
