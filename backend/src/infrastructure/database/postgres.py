from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel

from core import settings

_logger = structlog.get_logger(__name__)

_engine = None
_session_factory = None


async def init_db() -> None:
    global _engine, _session_factory

    _engine = create_async_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=settings.app_env != "production",
    )

    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        autoflush=False,
    )

    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    _logger.info("database_connected", pool_size=10, max_overflow=20)


async def close_db() -> None:
    if _engine is not None:
        await _engine.dispose()
        _logger.info("database_disconnected")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    if _session_factory is None:
        raise RuntimeError("Database chưa được khởi tạo. Gọi init_db() trước.")

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dùng ngoài FastAPI — cho tools, background tasks, scripts."""
    if _session_factory is None:
        raise RuntimeError("Database chưa được khởi tạo.")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
