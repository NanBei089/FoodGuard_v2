from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

"""数据库引擎与会话生命周期管理。"""

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.APP_DEBUG,
)

sync_engine = create_engine(
    settings.DATABASE_SYNC_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.APP_DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 异步数据库会话依赖。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            # 请求处理失败时统一回滚，避免部分写入污染事务。
            await session.rollback()
            raise
        finally:
            await session.close()


def get_engine() -> AsyncEngine:
    """返回异步 SQLAlchemy Engine。"""
    return engine


@contextmanager
def get_sync_db() -> Generator[Session, None, None]:
    """同步数据库会话上下文，用于 Celery 等非异步运行环境。"""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_sync_engine() -> Engine:
    """返回同步 SQLAlchemy Engine。"""
    return sync_engine


__all__ = [
    "AsyncSessionLocal",
    "SyncSessionLocal",
    "engine",
    "get_db",
    "get_engine",
    "get_sync_db",
    "get_sync_engine",
    "sync_engine",
]
