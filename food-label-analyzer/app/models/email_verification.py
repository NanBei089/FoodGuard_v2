from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Index, String, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.models.enums import VerificationType


class EmailVerification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "email_verifications"
    __table_args__ = (
        Index("idx_email_verifications_email_type", "email", "type"),
        Index("idx_email_verifications_expired_at", "expired_at"),
        {"extend_existing": True},
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    type: Mapped[VerificationType] = mapped_column(
        PgEnum(VerificationType, name="verification_type", create_type=True),
        nullable=False,
    )
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    expired_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


__all__ = ["EmailVerification", "VerificationType"]
