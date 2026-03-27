from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserPreference(UUIDPrimaryKeyMixin, TimeStampMixin, Base):
    __tablename__ = "user_preferences"
    __table_args__ = ({"extend_existing": True},)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    focus_groups: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    health_conditions: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    allergies: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    user: Mapped["User"] = relationship(back_populates="preference")


__all__ = ["UserPreference"]
