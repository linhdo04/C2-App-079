"""Agent facade and production tool tests."""

import asyncio
import os
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest
from fakes import FakePolicyLLM

from agent import run_agent, stream_agent
from agent.prompts import SYSTEM_PROMPT
from agent.react import (
    Action,
    AgentLoopResult,
    CallableTool,
    ConversationMessage,
    InMemoryMemory,
    Memory,
    ReActStep,
    ReasoningDecision,
    Tool,
)
from agent.reasoners import (
    FallbackReasoner,
    FallbackRouteDecision,
    GeminiReasoner,
    LLMRoutedFallbackReasoner,
    LLMToolRouter,
    _extract_server_retry_delay,
    classify_llm_error,
)
from agent.tool_policy import SemanticToolPolicy
from agent.tools import CalculatorTool, SearchInput, SearchTool, TelemetryInput
from agent.tools.search import (
    FilteredSearchResult,
    RejectedSearchResult,
    SearchFilterDecision,
    SearchFilterInput,
    SearchResultFilter,
    UsableClaim,
)


class RateLimitError(Exception):
    status_code = 429


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


@pytest.mark.asyncio
async def test_search_tool_filters_observation_with_coverage() -> None:
    from agent.react import ToolContext

    class FakeClient:
        def search(self, *, query: str, max_results: int) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "title": "Rice market",
                        "content": "Prices increased this week.",
                        "url": "https://example.com/rice-market",
                    },
                    {
                        "title": "Unrelated",
                        "content": "Movie listings.",
                        "url": "https://example.com/movies",
                    },
                ]
            }

    class FakeFilter:
        async def filter(self, data: Any) -> SearchFilterDecision:
            assert data.question == "rice price"
            assert len(data.results) == 2
            return SearchFilterDecision(
                coverage="partial",
                relevant_results=[
                    FilteredSearchResult(
                        title="Rice market",
                        url="https://example.com/rice-market",
                        summary="Rice prices increased this week.",
                        usable_claims=[
                            UsableClaim(
                                claim="Prices increased this week.",
                                source_url="https://example.com/rice-market",
                            )
                        ],
                        relevance_reason="Directly discusses rice prices.",
                    )
                ],
                rejected_results=[
                    RejectedSearchResult(
                        title="Unrelated",
                        url="https://example.com/movies",
                        reason="Not about rice.",
                    )
                ],
            )

    tool = SearchTool.__new__(SearchTool)
    tool._client = FakeClient()
    setattr(tool, "_result_filter", FakeFilter())

    result = await tool.execute(
        SearchInput(query="rice price", max_results=2),
        ToolContext(goal="search"),
    )

    assert "Coverage: partial" in result
    assert "Rejected results: 1" in result
    assert "Rice market" in result
    assert "Prices increased this week." in result
    assert "https://example.com/rice-market" in result
    assert "Movie listings" not in result
    assert "https://example.com/movies" not in result


@pytest.mark.asyncio
async def test_search_tool_falls_back_to_raw_results_when_filter_fails() -> None:
    from agent.react import ToolContext

    class FakeClient:
        def search(self, *, query: str, max_results: int) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "title": "Rice market",
                        "content": "Prices increased this week.",
                        "url": "https://example.com/rice-market",
                    }
                ]
            }

    class FailingFilter:
        async def filter(self, data: Any) -> SearchFilterDecision:
            raise TimeoutError

    tool = SearchTool.__new__(SearchTool)
    tool._client = FakeClient()
    setattr(tool, "_result_filter", FailingFilter())

    result = await tool.execute(
        SearchInput(query="rice price", max_results=1),
        ToolContext(goal="search"),
    )

    assert "lọc kết quả thất bại" in result
    assert "Rice market" in result
    assert "Snippet: Prices increased this week." in result


@pytest.mark.asyncio
async def test_search_tool_drops_filter_results_with_unknown_urls() -> None:
    from agent.react import ToolContext

    class FakeClient:
        def search(self, *, query: str, max_results: int) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "title": "Rice market",
                        "content": "Prices increased this week.",
                        "url": "https://example.com/rice-market",
                    }
                ]
            }

    class BadUrlFilter:
        async def filter(self, data: Any) -> SearchFilterDecision:
            return SearchFilterDecision(
                coverage="insufficient",
                relevant_results=[
                    FilteredSearchResult(
                        title="Invented",
                        url="https://example.com/invented",
                        summary="Invented summary.",
                        usable_claims=[
                            UsableClaim(
                                claim="Invented claim.",
                                source_url="https://example.com/invented",
                            )
                        ],
                        relevance_reason="Invented reason.",
                    )
                ],
                rejected_results=[],
            )

    tool = SearchTool.__new__(SearchTool)
    tool._client = FakeClient()
    setattr(tool, "_result_filter", BadUrlFilter())

    result = await tool.execute(
        SearchInput(query="rice price", max_results=1),
        ToolContext(goal="search"),
    )

    assert "Coverage: insufficient" in result
    assert "Không tìm thấy nguồn đủ phù hợp" in result
    assert "Invented" not in result
    assert "https://example.com/invented" not in result


@pytest.mark.asyncio
async def test_search_tool_filters_trace_regression_noise() -> None:
    from agent.react import ToolContext

    class FakeClient:
        def search(self, *, query: str, max_results: int) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "title": "Weather for Gia Lai",
                        "content": "Gia Lai has rain and moderate humidity today.",
                        "url": "https://example.com/weather",
                    },
                    {
                        "title": "EPR compliance update",
                        "content": "Packaging rules for manufacturers.",
                        "url": "https://example.com/epr",
                    },
                ]
            }

    class TraceFilter:
        async def filter(self, data: Any) -> SearchFilterDecision:
            return SearchFilterDecision(
                coverage="partial",
                relevant_results=[
                    FilteredSearchResult(
                        title="Weather for Gia Lai",
                        url="https://example.com/weather",
                        summary="Gia Lai has rain and moderate humidity today.",
                        usable_claims=[
                            UsableClaim(
                                claim="Rain and moderate humidity are expected.",
                                source_url="https://example.com/weather",
                            )
                        ],
                        relevance_reason="Weather source matches the location.",
                    )
                ],
                rejected_results=[
                    RejectedSearchResult(
                        title="EPR compliance update",
                        url="https://example.com/epr",
                        reason="EPR compliance is unrelated to weather.",
                    )
                ],
            )

    tool = SearchTool.__new__(SearchTool)
    tool._client = FakeClient()
    setattr(tool, "_result_filter", TraceFilter())

    result = await tool.execute(
        SearchInput(query="weather Gia Lai", max_results=2),
        ToolContext(goal="search"),
    )

    assert "Weather for Gia Lai" in result
    assert "Rain and moderate humidity are expected." in result
    assert "EPR compliance update" not in result
    assert "https://example.com/epr" not in result


def test_system_prompt_requires_search_source_links() -> None:
    assert "numbered inline citation links" in SYSTEM_PROMPT
    assert "Do not add a separate" in SYSTEM_PROMPT


def test_react_prompt_limits_thought() -> None:
    from agent.prompts import REACT_PROMPT

    assert "one short sentence" in REACT_PROMPT


@pytest.mark.asyncio
async def test_gemini_reasoner_recovers_valid_json_from_raw_content_list() -> None:
    class FakeBoundLLM:
        async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
            return SimpleNamespace(
                content=[
                    'thought":"broken prefix',
                    (
                        '{"thought":"Recovered.","action":null,'
                        '"is_done":true,"final_answer":"Đã có câu trả lời."}'
                    ),
                ]
            )

    class FakeLLM:
        def __init__(self) -> None:
            self.bound_kwargs: dict[str, Any] = {}

        def bind(self, **kwargs: Any) -> Any:
            self.bound_kwargs = kwargs
            return FakeBoundLLM()

    llm = FakeLLM()
    reasoner = GeminiReasoner(llm, timeout_seconds=1)

    decision = await reasoner.decide("Trả lời ngắn", InMemoryMemory(), [])

    assert llm.bound_kwargs["response_mime_type"] == "application/json"
    assert llm.bound_kwargs["response_schema"]["title"] == "ReasoningDecision"
    assert decision.is_done is True
    assert decision.final_answer == "Đã có câu trả lời."


@pytest.mark.asyncio
async def test_gemini_reasoner_retries_retryable_llm_errors() -> None:
    class FakeBoundLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise RateLimitError
            return {
                "thought": "Recovered.",
                "action": None,
                "is_done": True,
                "final_answer": "Đã thử lại thành công.",
            }

    class FakeLLM:
        def __init__(self) -> None:
            self.bound = FakeBoundLLM()

        def bind(self, **kwargs: Any) -> Any:
            return self.bound

    llm = FakeLLM()
    reasoner = GeminiReasoner(
        llm,
        timeout_seconds=1,
        max_retries=1,
        backoff_seconds=0,
    )

    decision = await reasoner.decide("Trả lời ngắn", InMemoryMemory(), [])

    assert llm.bound.calls == 2
    assert decision.final_answer == "Đã thử lại thành công."


@pytest.mark.asyncio
async def test_search_result_filter_retries_retryable_llm_errors() -> None:
    class FakeBoundLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise RateLimitError
            return {
                "coverage": "sufficient",
                "relevant_results": [
                    {
                        "title": "Rice market",
                        "url": "https://example.com/rice",
                        "summary": "Rice prices increased.",
                        "usable_claims": [
                            {
                                "claim": "Rice prices increased.",
                                "source_url": "https://example.com/rice",
                            }
                        ],
                        "relevance_reason": "Directly relevant.",
                    }
                ],
                "rejected_results": [],
            }

    class FakeLLM:
        def __init__(self) -> None:
            self.bound = FakeBoundLLM()

        def bind(self, **kwargs: Any) -> Any:
            return self.bound

    llm = FakeLLM()
    result_filter = SearchResultFilter(
        llm,
        timeout_seconds=1,
        max_retries=1,
        backoff_seconds=0,
    )

    decision = await result_filter.filter(
        SearchFilterInput(
            question="rice price",
            results=[
                {
                    "title": "Rice market",
                    "url": "https://example.com/rice",
                    "content": "Rice prices increased.",
                }
            ],
        )
    )

    assert llm.bound.calls == 2
    assert decision.coverage == "sufficient"
    assert decision.relevant_results[0].url == "https://example.com/rice"


@pytest.mark.asyncio
async def test_llm_routed_fallback_formats_search_results_as_citations() -> None:
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
    reasoner = LLMRoutedFallbackReasoner(None)

    answer = await reasoner.finalize("Gợi ý chăm sóc hồ tiêu tại Gia Lai", memory)

    assert "Thông tin nổi bật" in answer
    assert "[1](https://example.com/ho-tieu)" in answer
    assert "Nguồn tham khảo" not in answer
    assert "Title:" not in answer
    assert "URL:" not in answer
    assert "Snippet:" not in answer


@pytest.mark.asyncio
async def test_provider_fallback_uses_llm_router_selected_search() -> None:
    class FailingReasoner:
        async def decide(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> ReasoningDecision:
            raise TimeoutError

        async def finalize(self, goal: str, memory: Memory) -> str:
            raise TimeoutError

    class FakeRouter(LLMToolRouter):
        def __init__(self) -> None:
            pass

        async def route(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> FallbackRouteDecision:
            return FallbackRouteDecision(
                tool="search",
                input={"query": goal, "max_results": 3},
                reason="Needs web evidence.",
            )

    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )
    reasoner = FallbackReasoner(
        FailingReasoner(),
        LLMRoutedFallbackReasoner(FakeRouter()),
    )

    decision = await reasoner.decide(
        "chăm sóc hồ tiêu mùa mưa", InMemoryMemory(), (search_tool,)
    )

    assert decision.action == Action(
        tool="search",
        input={"query": "chăm sóc hồ tiêu mùa mưa", "max_results": 3},
    )


@pytest.mark.asyncio
async def test_semantic_tool_policy_uses_user_telemetry_before_search() -> None:
    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    telemetry_tool = CallableTool(
        "telemetry",
        "Read recent temperature and humidity owned by the user.",
        handler,
        input_model=TelemetryInput,
    )
    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )
    question = "Thời tiết tuần này ảnh hưởng thế nào đến lịch canh tác?"
    llm = FakePolicyLLM(
        {
            "actions": [
                {
                    "tool": "telemetry",
                    "input": {"limit": 50},
                    "reason": "Needs first-party field conditions.",
                },
                {
                    "tool": "search",
                    "input": {
                        "query": question,
                        "max_results": 5,
                    },
                    "reason": "Needs external forecast.",
                },
            ],
            "rationale": "Use telemetry before external forecast.",
        }
    )
    policy = SemanticToolPolicy(llm, timeout_seconds=1)

    decision = await policy.decide(
        question,
        InMemoryMemory(),
        (search_tool, telemetry_tool),
    )

    assert decision == Action(tool="telemetry", input={"limit": 50})
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_semantic_tool_policy_adds_forecast_search_after_telemetry() -> None:
    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    telemetry_tool = CallableTool(
        "telemetry",
        "Read recent temperature and humidity owned by the user.",
        handler,
        input_model=TelemetryInput,
    )
    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )
    memory = InMemoryMemory()
    memory.add(
        ReActStep(
            thought="Use telemetry.",
            action=Action(tool="telemetry", input={"limit": 50}),
            observation="Nhiệt độ mới nhất 31°C.",
        )
    )
    question = "Thời tiết tuần này ảnh hưởng thế nào đến lịch canh tác?"
    llm = FakePolicyLLM(
        {
            "actions": [
                {
                    "tool": "telemetry",
                    "input": {"limit": 50},
                    "reason": "Needs first-party field conditions.",
                },
                {
                    "tool": "search",
                    "input": {
                        "query": question,
                        "max_results": 5,
                    },
                    "reason": "Needs external forecast.",
                },
            ],
            "rationale": "Use telemetry first, then forecast.",
        }
    )
    policy = SemanticToolPolicy(llm, timeout_seconds=1)

    decision = await policy.decide(
        question,
        memory,
        (search_tool, telemetry_tool),
    )

    assert decision == Action(
        tool="search",
        input={
            "query": question,
            "max_results": 5,
        },
    )


@pytest.mark.asyncio
async def test_llm_tool_router_retries_retryable_llm_errors() -> None:
    class FakeBoundLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise RateLimitError
            return {
                "tool": "search",
                "input": {"query": "hồ tiêu", "max_results": 2},
                "reason": "Needs current web information.",
            }

    class FakeLLM:
        def __init__(self) -> None:
            self.bound = FakeBoundLLM()

        def bind(self, **kwargs: Any) -> Any:
            return self.bound

    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )
    llm = FakeLLM()
    router = LLMToolRouter(
        llm,
        timeout_seconds=1,
        max_retries=1,
        backoff_seconds=0,
    )

    decision = await router.route("hồ tiêu", InMemoryMemory(), (search_tool,))

    assert llm.bound.calls == 2
    assert decision.tool == "search"
    assert decision.input == {"query": "hồ tiêu", "max_results": 2}


@pytest.mark.asyncio
async def test_llm_routed_fallback_uses_calculator_when_router_input_is_valid() -> None:
    class FakeRouter(LLMToolRouter):
        def __init__(self) -> None:
            pass

        async def route(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> FallbackRouteDecision:
            return FallbackRouteDecision(
                tool="calculator",
                input={"expression": "6 * 7"},
                reason="Pure arithmetic.",
            )

    reasoner = LLMRoutedFallbackReasoner(FakeRouter())

    decision = await reasoner.decide("6 * 7", InMemoryMemory(), (CalculatorTool(),))

    assert decision.action == Action(
        tool="calculator",
        input={"expression": "6 * 7"},
    )


@pytest.mark.asyncio
async def test_llm_routed_fallback_defaults_to_search_for_invalid_router_input() -> (
    None
):
    class FakeRouter(LLMToolRouter):
        def __init__(self) -> None:
            pass

        async def route(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> FallbackRouteDecision:
            return FallbackRouteDecision(
                tool="calculator",
                input={"expression": ""},
                reason="Invalid calculator input.",
            )

    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )
    reasoner = LLMRoutedFallbackReasoner(FakeRouter())

    decision = await reasoner.decide(
        "thông tin canh tác mới", InMemoryMemory(), (search_tool, CalculatorTool())
    )

    assert decision.action == Action(
        tool="search",
        input={"query": "thông tin canh tác mới", "max_results": 5},
    )


@pytest.mark.asyncio
async def test_llm_routed_fallback_defaults_to_search_when_router_fails() -> None:
    class FailingRouter(LLMToolRouter):
        def __init__(self) -> None:
            pass

        async def route(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> FallbackRouteDecision:
            raise TimeoutError

    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )
    reasoner = LLMRoutedFallbackReasoner(FailingRouter())

    decision = await reasoner.decide(
        "khuyến nghị tưới tiêu", InMemoryMemory(), (search_tool,)
    )

    assert decision.action == Action(
        tool="search",
        input={"query": "khuyến nghị tưới tiêu", "max_results": 5},
    )


@pytest.mark.asyncio
async def test_llm_routed_fallback_without_search_returns_clear_error() -> None:
    class FailingRouter(LLMToolRouter):
        def __init__(self) -> None:
            pass

        async def route(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> FallbackRouteDecision:
            raise TimeoutError

    reasoner = LLMRoutedFallbackReasoner(FailingRouter())

    decision = await reasoner.decide(
        "câu hỏi mở", InMemoryMemory(), (CalculatorTool(),)
    )

    assert decision.is_done is True
    assert decision.final_answer is not None
    assert "fallback router" in decision.final_answer
    assert "Tôi chưa có đủ dữ liệu" not in decision.final_answer


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


def test_classify_llm_error_rate_limit_by_status_code() -> None:
    result = classify_llm_error(RateLimitError())
    assert result.error_code == "rate_limit"
    assert result.http_status == 503


def test_classify_llm_error_rate_limit_by_message() -> None:
    result = classify_llm_error(RuntimeError("429 rate limit exceeded"))
    assert result.error_code == "rate_limit"
    assert result.http_status == 503


def test_classify_llm_error_timeout() -> None:
    result = classify_llm_error(TimeoutError())
    assert result.error_code == "timeout"
    assert result.http_status == 504


def test_classify_llm_error_provider_unavailable() -> None:
    class ServerError(Exception):
        status_code = 503

    result = classify_llm_error(ServerError())
    assert result.error_code == "provider_unavailable"
    assert result.http_status == 503


def test_classify_llm_error_deadline_exceeded_maps_to_timeout() -> None:
    class DeadlineError(Exception):
        code = "DEADLINE_EXCEEDED"

    result = classify_llm_error(DeadlineError())
    assert result.error_code == "timeout"
    assert result.http_status == 504


def test_retryable_markers_cover_same_set_as_classify() -> None:
    from agent.reasoners import (
        _LLM_RETRYABLE_MESSAGE_MARKERS,
        _RATE_LIMIT_MARKERS,
        _UNAVAILABLE_MARKERS,
    )

    assert set(_LLM_RETRYABLE_MESSAGE_MARKERS) == set(_RATE_LIMIT_MARKERS) | set(
        _UNAVAILABLE_MARKERS
    )


def test_classify_llm_error_connection() -> None:
    result = classify_llm_error(ConnectionError("network unreachable"))
    assert result.error_code == "service_unavailable"
    assert result.http_status == 503


def test_classify_llm_error_generic_falls_back_to_internal() -> None:
    result = classify_llm_error(ValueError("unexpected value"))
    assert result.error_code == "internal_error"
    assert result.http_status == 500


def test_classify_llm_error_message_does_not_leak_details() -> None:
    result = classify_llm_error(RuntimeError("secret internal key abc123"))
    assert "abc123" not in result.message
    assert "secret" not in result.message


def test_extract_server_retry_delay_from_human_readable_message() -> None:
    exc = RuntimeError(
        "429 RESOURCE_EXHAUSTED. Please retry in 28.823862733s after the quota resets."
    )
    assert _extract_server_retry_delay(exc) == pytest.approx(28.823862733)


def test_extract_server_retry_delay_from_retry_info_detail() -> None:
    exc = RuntimeError("{'retryDelay': '53s', '@type': 'google.rpc.RetryInfo'}")
    assert _extract_server_retry_delay(exc) == pytest.approx(53.0)


def test_extract_server_retry_delay_returns_none_when_absent() -> None:
    assert _extract_server_retry_delay(RuntimeError("quota exceeded")) is None
    assert _extract_server_retry_delay(RateLimitError()) is None


@pytest.mark.asyncio
async def test_ainvoke_llm_with_retry_uses_server_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry should sleep for the server-suggested delay, not the fixed backoff."""
    from agent.reasoners import _ainvoke_llm_with_retry

    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = 0

    async def invoke() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("429 quota exceeded. Please retry in 42s.")
        return "ok"

    result = await _ainvoke_llm_with_retry(
        invoke,
        operation="test",
        timeout_seconds=5,
        max_retries=1,
        backoff_seconds=0.5,
    )

    assert result == "ok"
    assert calls == 2
    assert len(slept) == 1
    assert slept[0] == pytest.approx(42.0)


@pytest.mark.asyncio
async def test_ainvoke_llm_with_retry_caps_server_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server delay above the cap should be clamped."""
    from agent.reasoners import _ainvoke_llm_with_retry

    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = 0

    async def invoke() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("429 quota exceeded. Please retry in 999s.")
        return "ok"

    await _ainvoke_llm_with_retry(
        invoke,
        operation="test",
        timeout_seconds=5,
        max_retries=1,
        backoff_seconds=0.5,
    )

    assert slept[0] == pytest.approx(120.0)


@pytest.mark.asyncio
async def test_ainvoke_llm_with_retry_falls_back_to_backoff_without_server_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no server delay hint, exponential backoff should be used."""
    from agent.reasoners import _ainvoke_llm_with_retry

    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = 0

    async def invoke() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RateLimitError()
        return "ok"

    await _ainvoke_llm_with_retry(
        invoke,
        operation="test",
        timeout_seconds=5,
        max_retries=1,
        backoff_seconds=1.5,
    )

    assert slept[0] == pytest.approx(1.5)


@pytest.mark.skipif(
    os.getenv("RUN_AGENT_INTEGRATION_TESTS") != "1",
    reason="Set RUN_AGENT_INTEGRATION_TESTS=1 to call Gemini.",
)
@pytest.mark.asyncio
async def test_gemini_agent_integration_opt_in() -> None:
    answer = await run_agent("Trả lời ngắn gọn: 2 + 2 bằng bao nhiêu?")
    assert answer.strip()
