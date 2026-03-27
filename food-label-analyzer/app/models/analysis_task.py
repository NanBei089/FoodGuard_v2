from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import TIMESTAMP, ForeignKey, Index, String, Text, desc
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin, UUIDPrimaryKeyMixin
from app.models.enums import TaskStatus

if TYPE_CHECKING:
    from app.models.report import Report
    from app.models.user import User


class AnalysisTask(UUIDPrimaryKeyMixin, TimeStampMixin, Base):
    __tablename__ = "analysis_tasks"
    __table_args__ = (
        Index("idx_analysis_tasks_user_id", "user_id"),
        Index("idx_analysis_tasks_status", "status"),
        Index("idx_analysis_tasks_user_status", "user_id", "status"),
        Index("idx_analysis_tasks_created_at", desc("created_at")),
        {"extend_existing": True},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    image_key: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        PgEnum(
            TaskStatus,
            name="task_status",
            create_type=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        server_default=TaskStatus.PENDING.value,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    user: Mapped["User"] = relationship(back_populates="tasks")
    report: Mapped["Report | None"] = relationship(
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
    )


__all__ = ["AnalysisTask", "TaskStatus"]
