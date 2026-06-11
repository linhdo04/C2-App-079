"""Agent facade and production tool tests."""

import os
from pathlib import Path
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


@pytest.mark.skipif(
    os.getenv("RUN_AGENT_INTEGRATION_TESTS") != "1",
    reason="Set RUN_AGENT_INTEGRATION_TESTS=1 to call Gemini.",
)
@pytest.mark.asyncio
async def test_gemini_agent_integration_opt_in() -> None:
    answer = await run_agent("Trả lời ngắn gọn: 2 + 2 bằng bao nhiêu?")
    assert answer.strip()
