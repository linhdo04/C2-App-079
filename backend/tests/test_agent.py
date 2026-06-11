"""Agent facade and production tool tests."""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from agent import run_agent, stream_agent
from agent.react import AgentLoopResult, ConversationMessage
from agent.tools import CalculatorTool, DocumentSearchTool


@pytest.mark.asyncio
async def test_calculator_rejects_unsafe_and_large_expressions() -> None:
    from agent.react import ToolContext
    from agent.tools.calculator import CalculatorInput

    tool = CalculatorTool()
    context = ToolContext(goal="calculate")
    valid = await tool.execute(CalculatorInput(expression="(6 + 4) * 3"), context)
    unsafe = await tool.execute(
        CalculatorInput(expression="__import__('os').system('id')"), context
    )
    huge = await tool.execute(CalculatorInput(expression="10 ** 1000"), context)
    assert valid == "30"
    assert "không hợp lệ" in unsafe
    assert "không hợp lệ" in huge


@pytest.mark.asyncio
async def test_document_search_is_disabled_by_default() -> None:
    from agent.react import ToolContext
    from agent.tools.documents import DocumentSearchInput

    result = await DocumentSearchTool([]).execute(
        DocumentSearchInput(query="rice"),
        ToolContext(goal="search"),
    )
    assert result == "Document search is not configured."


@pytest.mark.asyncio
async def test_document_search_blocks_symlink_escape(tmp_path: Path) -> None:
    from agent.react import ToolContext
    from agent.tools.documents import DocumentSearchInput

    root = tmp_path / "root"
    root.mkdir()
    (root / "safe.md").write_text("rice handbook", encoding="utf-8")
    outside = tmp_path / "secret.md"
    outside.write_text("rice secret", encoding="utf-8")
    (root / "escape.md").symlink_to(outside)
    result = await DocumentSearchTool([str(root)]).execute(
        DocumentSearchInput(query="rice"),
        ToolContext(goal="search"),
    )
    assert "safe.md" in result
    assert "secret" not in result
    assert "escape.md" not in result


@pytest.mark.asyncio
async def test_document_search_blocks_file_swap_to_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.react import ToolContext
    from agent.tools.documents import DocumentSearchInput

    root = tmp_path / "root"
    root.mkdir()
    candidate = root / "guide.md"
    candidate.write_text("rice handbook", encoding="utf-8")
    outside = tmp_path / "secret.md"
    outside.write_text("rice secret", encoding="utf-8")
    original_is_symlink = Path.is_symlink
    swapped = False

    def swap_after_check(path: Path) -> bool:
        nonlocal swapped
        is_symlink = original_is_symlink(path)
        if path == candidate and not swapped:
            swapped = True
            path.unlink()
            path.symlink_to(outside)
        return is_symlink

    monkeypatch.setattr(Path, "is_symlink", swap_after_check)
    result = await DocumentSearchTool([str(root)]).execute(
        DocumentSearchInput(query="rice"),
        ToolContext(goal="search"),
    )

    assert result == "No matching documents."
    assert "secret" not in result


@pytest.mark.asyncio
async def test_run_agent_forwards_bounded_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_memory: Any = None

    class FakeAgent:
        async def run(self, goal: str, **kwargs: Any) -> AgentLoopResult:
            nonlocal seen_memory
            seen_memory = kwargs["memory"]
            return AgentLoopResult("answer", True, 1, (), "done", "run")

    monkeypatch.setattr("agent.agent.default_agent", FakeAgent())
    answer = await run_agent(
        "question",
        user_id=7,
        history=[ConversationMessage(role="user", content="previous")],
    )
    assert answer == "answer"
    assert seen_memory.conversation()[0].content == "previous"


@pytest.mark.asyncio
async def test_stream_agent_emits_live_tool_status_and_incremental_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAgent:
        async def run(self, goal: str, **kwargs: Any) -> AgentLoopResult:
            from agent.react import AgentEvent

            await kwargs["on_event"](
                AgentEvent("tool_started", "run", 1, tool="search")
            )
            return AgentLoopResult(
                "abcdefghijklmnopqrstuvwxyz0123456789",
                True,
                1,
                (),
                "done",
                "run",
            )

    monkeypatch.setattr("agent.agent.default_agent", FakeAgent())
    events = [event async for event in stream_agent("question", user_id=7)]
    assert events[0]["phase"] == "routing"
    assert events[1]["tool"] == "search"
    assert events[2]["phase"] == "synthesis"
    tokens = [event["content"] for event in events if event["event"] == "token"]
    assert len(tokens) == 2
    assert "".join(tokens) == "abcdefghijklmnopqrstuvwxyz0123456789"


@pytest.mark.asyncio
async def test_stream_agent_does_not_generate_final_answer_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnexpectedStreamingReasoner:
        async def stream_finalize(self, *args: Any) -> Any:
            if False:
                yield ""
            raise AssertionError("final answer must not be generated twice")

    class FakeAgent:
        loop = SimpleNamespace(reasoner=UnexpectedStreamingReasoner())

        async def run(self, goal: str, **kwargs: Any) -> AgentLoopResult:
            return AgentLoopResult("single final answer", True, 1, (), "done", "run")

    monkeypatch.setattr("agent.agent.default_agent", FakeAgent())
    events = [event async for event in stream_agent("question")]

    assert (
        "".join(event["content"] for event in events if event["event"] == "token")
        == "single final answer"
    )


@pytest.mark.asyncio
async def test_stream_agent_cancels_background_task_when_client_disconnects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingAgent:
        async def run(self, goal: str, **kwargs: Any) -> AgentLoopResult:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            raise AssertionError("blocking agent unexpectedly completed")

    monkeypatch.setattr("agent.agent.default_agent", BlockingAgent())
    events = stream_agent("question")

    assert (await anext(events))["phase"] == "routing"
    await asyncio.wait_for(started.wait(), timeout=1)
    close_stream = getattr(events, "aclose")
    await close_stream()

    await asyncio.wait_for(cancelled.wait(), timeout=1)


@pytest.mark.skipif(
    os.getenv("RUN_AGENT_INTEGRATION_TESTS") != "1",
    reason="Set RUN_AGENT_INTEGRATION_TESTS=1 to call Gemini.",
)
@pytest.mark.asyncio
async def test_gemini_agent_integration_opt_in() -> None:
    answer = await run_agent("Trả lời ngắn gọn: 2 + 2 bằng bao nhiêu?")
    assert answer.strip()
