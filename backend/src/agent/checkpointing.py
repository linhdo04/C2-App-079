"""LangGraph checkpoint lifecycle for the production agent."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any
from urllib.parse import quote

import structlog

from core import settings

logger = structlog.get_logger(__name__)

_checkpointer: Any | None = None
_checkpointer_context: Any | None = None


def _postgres_checkpoint_url() -> str:
    user = quote(settings.postgres_user, safe="")
    password = quote(settings.postgres_password, safe="")
    host = settings.postgres_host
    port = settings.postgres_port
    database = quote(settings.postgres_db, safe="")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def init_agent_checkpointer() -> None:
    """Initialize the process-wide LangGraph Postgres checkpointer if enabled."""
    global _checkpointer, _checkpointer_context
    if not settings.agent_checkpointing_enabled:
        logger.info("agent_checkpointer_disabled")
        return
    if _checkpointer is not None:
        return

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    _checkpointer_context = AsyncPostgresSaver.from_conn_string(
        _postgres_checkpoint_url()
    )
    _checkpointer = await _checkpointer_context.__aenter__()
    if settings.langgraph_checkpoint_setup_on_start:
        await _checkpointer.setup()
    logger.info(
        "agent_checkpointer_initialized",
        setup_on_start=settings.langgraph_checkpoint_setup_on_start,
    )


async def close_agent_checkpointer() -> None:
    """Close the process-wide LangGraph Postgres checkpointer."""
    global _checkpointer, _checkpointer_context
    if _checkpointer_context is None:
        _checkpointer = None
        return
    exc_type: type[BaseException] | None = None
    exc: BaseException | None = None
    tb: TracebackType | None = None
    await _checkpointer_context.__aexit__(exc_type, exc, tb)
    _checkpointer = None
    _checkpointer_context = None
    logger.info("agent_checkpointer_closed")


def get_agent_checkpointer() -> Any | None:
    """Return the initialized checkpointer, or None when disabled/unavailable."""
    return _checkpointer


@asynccontextmanager
async def temporary_agent_checkpointer(checkpointer: Any) -> AsyncIterator[None]:
    """Temporarily override the global checkpointer in tests."""
    global _checkpointer
    previous = _checkpointer
    _checkpointer = checkpointer
    try:
        yield
    finally:
        _checkpointer = previous


__all__ = [
    "close_agent_checkpointer",
    "get_agent_checkpointer",
    "init_agent_checkpointer",
    "temporary_agent_checkpointer",
]
