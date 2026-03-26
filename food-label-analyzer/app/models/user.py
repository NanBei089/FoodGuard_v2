from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.analysis_task import AnalysisTask
    from app.models.password_reset import PasswordResetToken
    from app.models.report import Report


class User(UUIDPrimaryKeyMixin, TimeStampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("idx_users_is_active", "is_active"), {"extend_existing": True})

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    tasks: Mapped[list["AnalysisTask"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


__all__ = ["User"]
