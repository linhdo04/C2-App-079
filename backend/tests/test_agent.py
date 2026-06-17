"""Agent facade and production tool tests."""

import asyncio
import os
from types import SimpleNamespace
from typing import Any

import pytest

from agent import run_agent, stream_agent
from agent.prompts import SYSTEM_PROMPT
from agent.react import (
    Action,
    AgentLoopResult,
    ConversationMessage,
    InMemoryMemory,
    ReActStep,
)
from agent.reasoners import HeuristicReasoner
from agent.tools import CalculatorTool, SearchInput, SearchTool


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
async def test_search_tool_includes_result_links() -> None:
    from agent.react import ToolContext

    class FakeClient:
        def search(self, *, query: str, max_results: int) -> dict[str, Any]:
            assert query == "rice price"
            assert max_results == 1
            return {
                "results": [
                    {
                        "title": "Rice market",
                        "content": "Prices increased this week.",
                        "url": "https://example.com/rice-market",
                    }
                ]
            }

    tool = SearchTool.__new__(SearchTool)
    tool._client = FakeClient()

    result = await tool.execute(
        SearchInput(query="rice price", max_results=1),
        ToolContext(goal="search"),
    )

    assert "Rice market" in result
    assert "Prices increased this week." in result
    assert "URL: https://example.com/rice-market" in result


def test_system_prompt_requires_search_source_links() -> None:
    assert "numbered inline citations" in SYSTEM_PROMPT
    assert "[Source title](URL)" in SYSTEM_PROMPT
    assert "Nguồn tham khảo" in SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_heuristic_fallback_formats_search_results_as_citations() -> None:
    memory = InMemoryMemory()
    memory.add(
        ReActStep(
            thought="Use search.",
            action=Action(tool="search", input={"query": "chăm sóc hồ tiêu Gia Lai"}),
            observation=(
                "- Title: HƯỚNG DẪN QUY TRÌNH TRỒNG VÀ CHĂM SÓC CÂY HỒ TIÊU\n"
                "  URL: https://example.com/ho-tieu\n"
                "  Snippet: Trước khi trồng cần chuẩn bị đất và bón lót phân "
                "chuồng hoai.\n\n"
                "- Title: Chăm sóc cây hồ tiêu vào mùa mưa\n"
                "  URL: https://example.com/mua-mua\n"
                "  Snippet: Cần kiểm soát thoát nước và bổ sung hữu cơ."
            ),
        )
    )
    reasoner = HeuristicReasoner(lambda _: [])

    answer = await reasoner.finalize("Gợi ý chăm sóc hồ tiêu tại Gia Lai", memory)

    assert "Thông tin nổi bật" in answer
    assert "Nguồn tham khảo" in answer
    assert "[1]" in answer
    assert "1. [HƯỚNG DẪN QUY TRÌNH TRỒNG VÀ CHĂM SÓC CÂY HỒ TIÊU]" in answer
    assert "Title:" not in answer
    assert "URL:" not in answer
    assert "Snippet:" not in answer


@pytest.mark.asyncio
async def test_run_agent_forwards_bounded_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_memory: Any = None
    seen_session_id: str | None = None

    class FakeAgent:
        async def run(self, goal: str, **kwargs: Any) -> AgentLoopResult:
            nonlocal seen_memory, seen_session_id
            seen_memory = kwargs["memory"]
            seen_session_id = kwargs["session_id"]
            return AgentLoopResult("answer", True, 1, (), "done", "run")

    monkeypatch.setattr("agent.agent.default_agent", FakeAgent())
    answer = await run_agent(
        "question",
        user_id=7,
        session_id="chat-42",
        history=[ConversationMessage(role="user", content="previous")],
    )
    assert answer == "answer"
    assert seen_memory.conversation()[0].content == "previous"
    assert seen_session_id == "chat-42"


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
