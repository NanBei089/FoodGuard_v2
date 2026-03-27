from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    desc,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimeStampMixin, UUIDPrimaryKeyMixin
from app.models.enums import NutritionParseSource

if TYPE_CHECKING:
    from app.models.analysis_task import AnalysisTask
    from app.models.user import User


class Report(UUIDPrimaryKeyMixin, TimeStampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_reports_score_range"),
        Index("idx_reports_user_id_created_at", "user_id", desc("created_at")),
        Index("idx_reports_score", "score"),
        {"extend_existing": True},
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingredients_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    nutrition_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    nutrition_parse_source: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    rag_results_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    llm_output_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    artifact_urls: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    task: Mapped["AnalysisTask"] = relationship(back_populates="report")
    user: Mapped["User"] = relationship(back_populates="reports")


__all__ = ["NutritionParseSource", "Report"]
