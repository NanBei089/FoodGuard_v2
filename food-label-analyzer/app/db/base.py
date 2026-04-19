from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

"""SQLAlchemy 声明式基类与通用模型 mixin。"""


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。"""

    pass


class UUIDPrimaryKeyMixin:
    """为模型提供 UUID 主键。"""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )


class TimeStampMixin:
    """为模型提供创建时间和更新时间字段。"""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CreatedAtMixin:
    """仅需要创建时间的模型 mixin。"""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


__all__ = ["Base", "CreatedAtMixin", "TimeStampMixin", "UUIDPrimaryKeyMixin"]
