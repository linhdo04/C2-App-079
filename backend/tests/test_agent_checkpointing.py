from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest

from agent import checkpointing
from core.config import settings


class FakeSaver:
    setup_calls = 0
    entered = False
    exited = False
    received_dsn = ""

    async def setup(self) -> None:
        type(self).setup_calls += 1

    @classmethod
    @asynccontextmanager
    async def from_conn_string(cls, conn_string: str) -> AsyncIterator["FakeSaver"]:
        cls.received_dsn = conn_string
        cls.entered = True
        saver = cls()
        try:
            yield saver
        finally:
            cls.exited = True


@pytest.mark.asyncio
async def test_agent_checkpointer_lifecycle_auto_setup(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "agent_checkpointing_enabled", True)
    monkeypatch.setattr(settings, "langgraph_checkpoint_setup_on_start", True)
    monkeypatch.setattr(settings, "postgres_user", "user")
    monkeypatch.setattr(settings, "postgres_password", "p@ss word")
    monkeypatch.setattr(settings, "postgres_host", "db")
    monkeypatch.setattr(settings, "postgres_port", 5432)
    monkeypatch.setattr(settings, "postgres_db", "agent db")
    monkeypatch.setattr(
        "langgraph.checkpoint.postgres.aio.AsyncPostgresSaver",
        FakeSaver,
    )
    monkeypatch.setattr(checkpointing, "_checkpointer", None)
    monkeypatch.setattr(checkpointing, "_checkpointer_context", None)

    await checkpointing.init_agent_checkpointer()

    assert FakeSaver.entered is True
    assert FakeSaver.setup_calls == 1
    assert (
        FakeSaver.received_dsn == "postgresql://user:p%40ss%20word@db:5432/agent%20db"
    )
    assert checkpointing.get_agent_checkpointer() is not None

    await checkpointing.close_agent_checkpointer()

    assert FakeSaver.exited is True
    assert checkpointing.get_agent_checkpointer() is None


@pytest.mark.asyncio
async def test_agent_checkpointer_disabled(monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "agent_checkpointing_enabled", False)
    monkeypatch.setattr(checkpointing, "_checkpointer", None)
    monkeypatch.setattr(checkpointing, "_checkpointer_context", None)

    await checkpointing.init_agent_checkpointer()

    assert checkpointing.get_agent_checkpointer() is None
