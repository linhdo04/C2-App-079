"""Regression tests for metadata-safe agent tracing."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast

import pytest

from agent import tracing
from agent.agent import run_agent, stream_agent
from agent.tracing import content_metadata, current_trace_context


class _FakeRun:
    def __init__(self) -> None:
        self.metadata: dict[str, Any] = {}
        self.outputs: dict[str, Any] = {}

    def set(self, *, metadata: dict[str, Any]) -> None:
        self.metadata = metadata

    def add_outputs(self, outputs: dict[str, Any]) -> None:
        self.outputs.update(outputs)


@pytest.fixture
def captured_traces(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    @contextmanager
    def fake_trace(name: str, **kwargs: Any) -> Iterator[_FakeRun]:
        run = _FakeRun()
        call = {"name": name, "run": run, **kwargs}
        calls.append(call)
        yield run

    monkeypatch.setattr("agent.tracing.settings.langsmith_api_key", "test-key")
    monkeypatch.setattr("agent.tracing.settings.langsmith_tracing", True)
    monkeypatch.setattr("agent.tracing._get_langsmith_client", lambda: object())
    monkeypatch.setattr("agent.tracing.trace", fake_trace)
    return calls


def test_content_metadata_is_stable_and_does_not_retain_content() -> None:
    secret = "farmer@example.com asks about field 7"

    metadata = content_metadata(secret, prefix="input")

    assert metadata["input_characters"] == len(secret)
    assert len(metadata["input_sha256"]) == 16
    assert secret not in repr(metadata)


def test_langsmith_client_hides_all_inputs_and_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_client(**kwargs: Any) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(tracing, "_langsmith_client", None)
    monkeypatch.setattr(tracing, "Client", fake_client)

    tracing._get_langsmith_client()

    assert captured["hide_inputs"] is True
    assert captured["hide_outputs"] is True


@pytest.mark.asyncio
async def test_pre_router_gets_root_trace_without_raw_payload(
    captured_traces: list[dict[str, Any]],
) -> None:
    question = "hello"

    answer = await run_agent(question, user_id=7, session_id="12")

    assert answer
    assert [call["name"] for call in captured_traces] == [
        "agent-run",
        "agent-pre-router",
    ]
    root = captured_traces[0]
    assert root["inputs"] == {}
    assert question not in repr(root)
    assert root["run"].metadata["route"] == "pre_router"
    assert root["run"].metadata["success"] is True
    assert current_trace_context() is None


@pytest.mark.asyncio
async def test_closing_fast_path_stream_closes_trace_and_resets_context(
    captured_traces: list[dict[str, Any]],
) -> None:
    events = stream_agent("hello")

    first = await anext(events)
    await cast(Any, events).aclose()

    assert first["event"] == "status"
    root = captured_traces[0]
    assert root["run"].metadata["route"] == "cancelled"
    assert root["run"].metadata["success"] is False
    assert current_trace_context() is None
