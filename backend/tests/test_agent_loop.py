"""Contract tests for the production ReAct loop."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
from fakes import FakePolicyLLM
from pydantic import BaseModel, Field

from agent.react import (
    Action,
    AgentEvent,
    AgentLoop,
    CallableTool,
    ConversationMessage,
    DoneOrMaxIterations,
    Executor,
    InMemoryMemory,
    Memory,
    ReasoningDecision,
    Tool,
    ToolContext,
    ToolRegistry,
)
from agent.tool_policy import SemanticToolPolicy
from agent.tools import SearchInput, TelemetryInput


class TextInput(BaseModel):
    text: str = Field(min_length=1)


class SequenceReasoner:
    def __init__(self, decisions: list[ReasoningDecision]) -> None:
        self.decisions = decisions
        self.calls = 0

    async def decide(
        self, goal: str, memory: Memory, tools: Sequence[Tool]
    ) -> ReasoningDecision:
        decision = self.decisions[min(self.calls, len(self.decisions) - 1)]
        self.calls += 1
        return decision

    async def finalize(self, goal: str, memory: Memory) -> str:
        return "safe finalization"


class SequenceToolPolicy:
    def __init__(self, actions: list[Action | None]) -> None:
        self.actions = actions
        self.calls = 0

    async def decide(
        self,
        goal: str,
        memory: Memory,
        tools: Sequence[Tool],
    ) -> Action | None:
        action = self.actions[min(self.calls, len(self.actions) - 1)]
        self.calls += 1
        return action


def create_loop(
    reasoner: Any,
    tools: list[Tool] | None = None,
    *,
    max_iterations: int = 4,
    max_retries: int = 1,
    backoff_seconds: float = 0,
    tool_policy: Any | None = None,
) -> AgentLoop:
    return AgentLoop(
        reasoner=reasoner,
        executor=Executor(
            ToolRegistry(tools or []),
            timeout_seconds=0.1,
            max_retries=max_retries,
            backoff_seconds=backoff_seconds,
        ),
        termination_condition=DoneOrMaxIterations(),
        max_iterations=max_iterations,
        tool_policy=tool_policy,
    )


@pytest.mark.asyncio
async def test_tool_adapts_to_langchain_structured_tool() -> None:
    async def echo(tool_input: BaseModel, context: ToolContext) -> str:
        data = TextInput.model_validate(tool_input)
        return f"{context.run_id}:{data.text}"

    tool = CallableTool("echo", "Echo input", echo, input_model=TextInput)
    langchain_tool = tool.as_langchain_tool(ToolContext(goal="goal", run_id="run-1"))

    assert langchain_tool.name == "echo"
    assert await langchain_tool.ainvoke({"text": "hello"}) == "run-1:hello"


@pytest.mark.asyncio
async def test_done_and_max_iterations_termination() -> None:
    done = SequenceReasoner(
        [ReasoningDecision(thought="Complete", is_done=True, final_answer="answer")]
    )
    result = await create_loop(done).run("goal")
    assert (result.done, result.termination_reason, result.final_response) == (
        True,
        "done",
        "answer",
    )

    async def echo(tool_input: BaseModel, context: ToolContext) -> str:
        return TextInput.model_validate(tool_input).text

    limited = SequenceReasoner(
        [
            ReasoningDecision(
                thought="One", action=Action(tool="echo", input={"text": "1"})
            ),
            ReasoningDecision(
                thought="Two", action=Action(tool="echo", input={"text": "2"})
            ),
        ]
    )
    result = await create_loop(
        limited,
        [CallableTool("echo", "Echo", echo, input_model=TextInput)],
        max_iterations=2,
    ).run("goal")
    assert result.termination_reason == "max_iterations"
    assert result.final_response == "safe finalization"


@pytest.mark.asyncio
async def test_tool_policy_runs_before_reasoner_decision() -> None:
    async def telemetry(tool_input: BaseModel, context: ToolContext) -> str:
        data = TelemetryInput.model_validate(tool_input)
        assert data.limit == 50
        return "Nhiệt độ mới nhất 31°C."

    telemetry_tool = CallableTool(
        "telemetry",
        "Read recent temperature and humidity owned by the user.",
        telemetry,
        input_model=TelemetryInput,
    )
    reasoner = SequenceReasoner(
        [ReasoningDecision(thought="Complete", is_done=True, final_answer="answer")]
    )

    result = await create_loop(
        reasoner,
        [telemetry_tool],
        tool_policy=SemanticToolPolicy(
            FakePolicyLLM(
                {
                    "actions": [
                        {
                            "tool": "telemetry",
                            "input": {"limit": 50},
                            "reason": "Needs first-party field conditions.",
                        }
                    ],
                    "rationale": "Use telemetry first.",
                }
            ),
            timeout_seconds=1,
        ),
    ).run("Độ ẩm ruộng tôi đang thế nào?")

    assert result.steps[0].action == Action(tool="telemetry", input={"limit": 50})
    assert result.final_response == "answer"
    assert reasoner.calls == 1


@pytest.mark.asyncio
async def test_exact_telemetry_skips_second_tool_policy_call() -> None:
    telemetry_calls = 0

    async def telemetry(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal telemetry_calls
        telemetry_calls += 1
        return (
            "Truy vấn telemetry theo chỉ số trong hôm nay:\n"
            "- Nhiệt độ cao nhất trong hôm nay: 35.0°C; "
            "thời điểm 12:09:33 ngày 23/06/2026 (giờ Việt Nam); "
            "thiết bị Cảm biến 01; mission Ruộng lúa\n"
            "- Đây là số đo lịch sử, không phải dự báo thời tiết."
        )

    telemetry_tool = CallableTool(
        "telemetry",
        "Read temperature and humidity owned by the user.",
        telemetry,
        input_model=TelemetryInput,
    )
    reasoner = SequenceReasoner(
        [
            ReasoningDecision(
                thought="Complete.",
                is_done=True,
                final_answer="Nhiệt độ cao nhất hôm nay là 35.0°C.",
            )
        ]
    )
    policy = SequenceToolPolicy(
        [Action(tool="telemetry", input={"query_kinds": ["temperature_max"]})]
    )

    result = await create_loop(
        reasoner,
        [telemetry_tool],
        tool_policy=policy,
    ).run("Nhiệt độ cao nhất hôm nay là bao nhiêu?")

    assert telemetry_calls == 1
    assert policy.calls == 1
    assert reasoner.calls == 1
    assert result.final_response == "Nhiệt độ cao nhất hôm nay là 35.0°C."


@pytest.mark.asyncio
async def test_exact_telemetry_keeps_second_policy_call_for_external_intent() -> None:
    search_calls = 0

    async def telemetry(tool_input: BaseModel, context: ToolContext) -> str:
        return "Nhiệt độ cao nhất trong hôm nay: 35.0°C."

    async def search(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal search_calls
        search_calls += 1
        return "Dự báo thời tiết hôm nay có mưa."

    telemetry_tool = CallableTool(
        "telemetry",
        "Read temperature and humidity owned by the user.",
        telemetry,
        input_model=TelemetryInput,
    )
    search_tool = CallableTool(
        "search",
        "Search web",
        search,
        input_model=SearchInput,
    )
    reasoner = SequenceReasoner(
        [
            ReasoningDecision(
                thought="Complete.",
                is_done=True,
                final_answer="Nhiệt độ cao nhất là 35.0°C và có mưa.",
            )
        ]
    )
    policy = SequenceToolPolicy(
        [
            Action(tool="telemetry", input={"query_kinds": ["temperature_max"]}),
            Action(tool="search", input={"query": "dự báo thời tiết hôm nay"}),
            None,
        ]
    )

    result = await create_loop(
        reasoner,
        [telemetry_tool, search_tool],
        tool_policy=policy,
    ).run("Nhiệt độ cao nhất hôm nay và dự báo thời tiết hôm nay thế nào?")

    assert policy.calls == 3
    assert search_calls == 1
    assert reasoner.calls == 1
    assert result.final_response == "Nhiệt độ cao nhất là 35.0°C và có mưa."


@pytest.mark.asyncio
async def test_reasoner_error_propagates_to_api_layer() -> None:
    class FailingReasoner:
        async def decide(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> ReasoningDecision:
            raise TimeoutError

        async def finalize(self, goal: str, memory: Memory) -> str:
            return "should not finalize"

    with pytest.raises(TimeoutError):
        await create_loop(FailingReasoner()).run("goal")


@pytest.mark.asyncio
async def test_empty_telemetry_blocks_implicit_search() -> None:
    telemetry_calls = 0
    search_calls = 0

    async def telemetry(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal telemetry_calls
        telemetry_calls += 1
        return (
            "Không có dữ liệu nhiệt độ hoặc độ ẩm cho người dùng trong ngày 18/06/2026."
        )

    async def search(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal search_calls
        search_calls += 1
        return "web result"

    reasoner = SequenceReasoner(
        [
            ReasoningDecision(
                thought="Use telemetry.",
                action=Action(
                    tool="telemetry",
                    input={"start_time": "2026-06-18T00:00:00Z"},
                ),
            ),
            ReasoningDecision(
                thought="Try web search.",
                action=Action(
                    tool="search",
                    input={"query": "nhiệt độ thấp nhất ngày 18"},
                ),
            ),
        ]
    )

    result = await create_loop(
        reasoner,
        [
            CallableTool(
                "telemetry",
                "Read temperature and humidity owned by the user.",
                telemetry,
                input_model=TelemetryInput,
            ),
            CallableTool(
                "search",
                "Search web",
                search,
                input_model=SearchInput,
            ),
        ],
    ).run("nhiệt độ thấp nhất ngày 18/06/2026 là bao nhiêu?")

    assert telemetry_calls == 1
    assert search_calls == 0
    assert result.done is True
    assert result.termination_reason == "done"
    assert "Không có dữ liệu nhiệt độ hoặc độ ẩm" in result.final_response
    assert "không dùng kết quả tìm kiếm web" in result.final_response


@pytest.mark.asyncio
async def test_empty_specific_telemetry_blocks_implicit_search() -> None:
    search_calls = 0

    async def telemetry(tool_input: BaseModel, context: ToolContext) -> str:
        return "Không có dữ liệu nhiệt độ trong hôm nay."

    async def search(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal search_calls
        search_calls += 1
        return "web result"

    reasoner = SequenceReasoner(
        [
            ReasoningDecision(
                thought="Use telemetry.",
                action=Action(
                    tool="telemetry",
                    input={"query_kinds": ["temperature_max"]},
                ),
            ),
            ReasoningDecision(
                thought="Try web search.",
                action=Action(
                    tool="search",
                    input={"query": "nhiệt độ cao nhất hôm nay"},
                ),
            ),
        ]
    )

    result = await create_loop(
        reasoner,
        [
            CallableTool(
                "telemetry",
                "Read temperature and humidity owned by the user.",
                telemetry,
                input_model=TelemetryInput,
            ),
            CallableTool(
                "search",
                "Search web",
                search,
                input_model=SearchInput,
            ),
        ],
    ).run("nhiệt độ cao nhất hôm nay là bao nhiêu?")

    assert search_calls == 0
    assert result.done is True
    assert "Không có dữ liệu nhiệt độ hoặc độ ẩm" in result.final_response
    assert "không dùng kết quả tìm kiếm web" in result.final_response


@pytest.mark.asyncio
async def test_empty_two_hour_specific_telemetry_blocks_implicit_search() -> None:
    search_calls = 0

    async def telemetry(tool_input: BaseModel, context: ToolContext) -> str:
        data = TelemetryInput.model_validate(tool_input)
        assert data.query_kinds == ["temperature_max"]
        assert data.temporal_intent is not None
        assert data.temporal_intent.count == 2
        assert data.temporal_intent.unit == "hour"
        return "Không có dữ liệu nhiệt độ trong 2 giờ qua."

    async def search(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal search_calls
        search_calls += 1
        return "web result"

    reasoner = SequenceReasoner(
        [
            ReasoningDecision(
                thought="Use telemetry.",
                action=Action(
                    tool="telemetry",
                    input={
                        "query_kinds": ["temperature_max"],
                        "temporal_intent": {
                            "kind": "rolling",
                            "count": 2,
                            "unit": "hour",
                        },
                    },
                ),
            ),
            ReasoningDecision(
                thought="Try web search.",
                action=Action(
                    tool="search",
                    input={"query": "nhiệt độ cao nhất 2 tiếng vừa rồi"},
                ),
            ),
        ]
    )

    result = await create_loop(
        reasoner,
        [
            CallableTool(
                "telemetry",
                "Read temperature and humidity owned by the user.",
                telemetry,
                input_model=TelemetryInput,
            ),
            CallableTool(
                "search",
                "Search web",
                search,
                input_model=SearchInput,
            ),
        ],
    ).run("trong hai tiếng vừa rồi nhiệt độ cao nhất là bao nhiêu?")

    assert search_calls == 0
    assert result.done is True
    assert "Không có dữ liệu nhiệt độ hoặc độ ẩm" in result.final_response
    assert "không dùng kết quả tìm kiếm web" in result.final_response


@pytest.mark.asyncio
async def test_empty_telemetry_allows_search_when_external_intent_is_explicit() -> None:
    search_calls = 0

    async def telemetry(tool_input: BaseModel, context: ToolContext) -> str:
        return "Không có dữ liệu nhiệt độ hoặc độ ẩm cho người dùng trong hôm nay."

    async def search(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal search_calls
        search_calls += 1
        return "Dự báo thời tiết hôm nay có mưa."

    reasoner = SequenceReasoner(
        [
            ReasoningDecision(
                thought="Use telemetry.",
                action=Action(tool="telemetry", input={"relative_range": "today"}),
            ),
            ReasoningDecision(
                thought="Use forecast search.",
                action=Action(
                    tool="search",
                    input={"query": "dự báo thời tiết hôm nay"},
                ),
            ),
            ReasoningDecision(
                thought="Complete.",
                is_done=True,
                final_answer="Dự báo thời tiết hôm nay có mưa.",
            ),
        ]
    )

    result = await create_loop(
        reasoner,
        [
            CallableTool(
                "telemetry",
                "Read temperature and humidity owned by the user.",
                telemetry,
                input_model=TelemetryInput,
            ),
            CallableTool(
                "search",
                "Search web",
                search,
                input_model=SearchInput,
            ),
        ],
    ).run("telemetry hôm nay và dự báo thời tiết hôm nay thế nào?")

    assert search_calls == 1
    assert result.final_response == "Dự báo thời tiết hôm nay có mưa."


@pytest.mark.asyncio
async def test_ambiguous_day_only_telemetry_date_asks_for_clarification() -> None:
    telemetry_calls = 0

    async def telemetry(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal telemetry_calls
        telemetry_calls += 1
        return "should not execute"

    reasoner = SequenceReasoner(
        [
            ReasoningDecision(
                thought="Use telemetry.",
                action=Action(
                    tool="telemetry",
                    input={
                        "start_time": "2024-05-18T00:00:00Z",
                        "end_time": "2024-05-18T23:59:59Z",
                    },
                ),
            )
        ]
    )

    result = await create_loop(
        reasoner,
        [
            CallableTool(
                "telemetry",
                "Read temperature and humidity owned by the user.",
                telemetry,
                input_model=TelemetryInput,
            )
        ],
    ).run("nhiệt độ thấp nhất trong ngày 18 là bao nhiêu?")

    assert telemetry_calls == 0
    assert result.done is True
    assert "ngày, tháng và năm" in result.final_response
    assert "không tự suy đoán tháng/năm" in result.final_response


@pytest.mark.asyncio
async def test_ambiguous_day_only_specific_telemetry_query_asks_for_clarification() -> (
    None
):
    telemetry_calls = 0

    async def telemetry(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal telemetry_calls
        telemetry_calls += 1
        return "should not execute"

    reasoner = SequenceReasoner(
        [
            ReasoningDecision(
                thought="Use telemetry.",
                action=Action(
                    tool="telemetry",
                    input={"query_kinds": ["temperature_min"]},
                ),
            )
        ]
    )

    result = await create_loop(
        reasoner,
        [
            CallableTool(
                "telemetry",
                "Read temperature and humidity owned by the user.",
                telemetry,
                input_model=TelemetryInput,
            )
        ],
    ).run("nhiệt độ thấp nhất trong ngày 18 là bao nhiêu?")

    assert telemetry_calls == 0
    assert result.done is True
    assert "ngày, tháng và năm" in result.final_response
    assert "không tự suy đoán tháng/năm" in result.final_response


@pytest.mark.asyncio
async def test_point_telemetry_query_with_missing_month_year_is_not_guarded() -> None:
    telemetry_calls = 0

    async def telemetry(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal telemetry_calls
        telemetry_calls += 1
        data = TelemetryInput.model_validate(tool_input)
        assert data.query_kinds == ["temperature_at"]
        return "Nhiệt độ gần 12:18:00 ngày 18/06/2026: 31.0°C."

    reasoner = SequenceReasoner(
        [
            ReasoningDecision(
                thought="Use telemetry.",
                action=Action(
                    tool="telemetry",
                    input={"query_kinds": ["temperature_at"]},
                ),
            ),
            ReasoningDecision(
                thought="Complete.",
                is_done=True,
                final_answer="Nhiệt độ gần 12:18 ngày 18 là 31.0°C.",
            ),
        ]
    )

    result = await create_loop(
        reasoner,
        [
            CallableTool(
                "telemetry",
                "Read temperature and humidity owned by the user.",
                telemetry,
                input_model=TelemetryInput,
            )
        ],
    ).run("nhiệt độ lúc 12:18 ngày 18 là bao nhiêu?")

    assert telemetry_calls == 1
    assert result.done is True
    assert result.final_response == "Nhiệt độ gần 12:18 ngày 18 là 31.0°C."


@pytest.mark.asyncio
async def test_duplicate_canonical_tool_call_stops_without_second_execution() -> None:
    calls = 0

    async def echo(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal calls
        calls += 1
        return "ok"

    reasoner = SequenceReasoner(
        [
            ReasoningDecision(
                thought="First",
                action=Action(tool="echo", input={"text": "same"}),
            )
        ]
    )
    result = await create_loop(
        reasoner,
        [CallableTool("echo", "Echo", echo, input_model=TextInput)],
    ).run("goal")
    assert calls == 1
    assert result.termination_reason == "no_progress"
    assert result.iterations == 2


@pytest.mark.asyncio
async def test_executor_validates_schema_and_does_not_retry_permanent_error() -> None:
    calls = 0

    async def fail(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal calls
        calls += 1
        raise ValueError("secret")

    executor = Executor(
        ToolRegistry(
            [
                CallableTool(
                    "tool",
                    "Tool",
                    fail,
                    input_model=TextInput,
                    retryable=True,
                )
            ]
        ),
        timeout_seconds=1,
        max_retries=3,
    )
    invalid = await executor.execute(
        Action(tool="tool", input={}),
        ToolContext(goal="goal"),
    )
    failed = await executor.execute(
        Action(tool="tool", input={"text": "x"}),
        ToolContext(goal="goal"),
    )
    missing = await executor.execute(
        Action(tool="missing", input={}),
        ToolContext(goal="goal"),
    )
    assert invalid.attempts == 0
    assert failed.attempts == 1
    assert missing.attempts == 0
    assert calls == 1
    assert "secret" not in failed.observation


@pytest.mark.asyncio
async def test_executor_retries_transient_errors_with_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    sleeps: list[float] = []

    async def flaky(tool_input: BaseModel, context: ToolContext) -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("temporary")
        return "ok"

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    executor = Executor(
        ToolRegistry(
            [
                CallableTool(
                    "tool",
                    "Tool",
                    flaky,
                    input_model=TextInput,
                    retryable=True,
                )
            ]
        ),
        timeout_seconds=1,
        max_retries=2,
        backoff_seconds=0.25,
    )
    result = await executor.execute(
        Action(tool="tool", input={"text": "x"}),
        ToolContext(goal="goal"),
    )
    assert result.succeeded is True
    assert result.attempts == 3
    assert sleeps == [0.25, 0.5]


@pytest.mark.asyncio
async def test_tool_started_event_precedes_completion() -> None:
    release = asyncio.Event()
    events: list[AgentEvent] = []

    async def slow(tool_input: BaseModel, context: ToolContext) -> str:
        await release.wait()
        return "ok"

    executor = Executor(
        ToolRegistry([CallableTool("tool", "Tool", slow, input_model=TextInput)]),
        timeout_seconds=1,
    )
    task = asyncio.create_task(
        executor.execute(
            Action(tool="tool", input={"text": "x"}),
            ToolContext(goal="goal", run_id="run"),
            on_event=events.append,
        )
    )
    await asyncio.sleep(0)
    assert [event.type for event in events] == ["tool_started"]
    release.set()
    await task
    assert [event.type for event in events] == [
        "tool_started",
        "tool_completed",
    ]


@pytest.mark.asyncio
async def test_agent_loop_stream_uses_langgraph_custom_statuses_and_tokens() -> None:
    async def search(tool_input: BaseModel, context: ToolContext) -> str:
        return "safe tool observation"

    reasoner = SequenceReasoner(
        [
            ReasoningDecision(
                thought="Need search",
                action=Action(tool="search", input={"text": "rice"}),
            ),
            ReasoningDecision(
                thought="Complete",
                is_done=True,
                final_answer="safe final answer",
            ),
        ]
    )
    loop = create_loop(
        reasoner,
        [CallableTool("search", "Search", search, input_model=TextInput)],
    )

    events = [event async for event in loop.stream("goal", session_id="chat-1")]

    statuses = [event for event in events if event["event"] == "status"]
    assert [status["phase"] for status in statuses] == [
        "routing",
        "routing",
        "tool",
        "routing",
        "synthesis",
    ]
    assert statuses[2]["tool"] == "search"
    token_chunks = [event["content"] for event in events if event["event"] == "token"]
    assert "".join(token_chunks) == "safe final answer"
    assert max(len(chunk) for chunk in token_chunks) <= 8
    assert events[-1]["event"] == "result"


@pytest.mark.asyncio
async def test_agent_loop_streams_final_synthesis_tokens_before_result() -> None:
    async def echo(tool_input: BaseModel, context: ToolContext) -> str:
        return TextInput.model_validate(tool_input).text

    class StreamingFinalReasoner(SequenceReasoner):
        def __init__(self) -> None:
            super().__init__(
                [
                    ReasoningDecision(
                        thought="Use tool",
                        action=Action(tool="echo", input={"text": "observation"}),
                    )
                ]
            )
            self.finalize_calls = 0

        async def finalize(self, goal: str, memory: Memory) -> str:
            self.finalize_calls += 1
            return "non-stream final"

        async def stream_finalize(
            self, goal: str, memory: Memory
        ) -> AsyncIterator[str]:
            yield "hello "
            await asyncio.sleep(0)
            yield "world"

    reasoner = StreamingFinalReasoner()
    loop = create_loop(
        reasoner,
        [CallableTool("echo", "Echo", echo, input_model=TextInput)],
        max_iterations=1,
    )

    events = [event async for event in loop.stream("goal")]
    token_indexes = [
        index for index, event in enumerate(events) if event["event"] == "token"
    ]
    result_index = next(
        index for index, event in enumerate(events) if event["event"] == "result"
    )

    assert token_indexes
    assert max(token_indexes) < result_index
    assert (
        "".join(event["content"] for event in events if event["event"] == "token")
        == "hello world"
    )
    assert events[result_index]["result"].final_response == "hello world"
    assert reasoner.finalize_calls == 0


def test_message_stream_token_only_allows_finalize_node() -> None:
    class Chunk:
        content = "token"

    assert AgentLoop._message_stream_token((Chunk(), {"langgraph_node": "plan"})) == ""
    assert (
        AgentLoop._message_stream_token(
            (Chunk(), {"langgraph_node": "finalize", "tags": ["nostream"]})
        )
        == ""
    )
    assert (
        AgentLoop._message_stream_token((Chunk(), {"langgraph_node": "finalize"}))
        == "token"
    )


def test_graph_config_uses_chat_thread_id_for_checkpointing() -> None:
    loop = create_loop(SequenceReasoner([]))

    config = loop._graph_config(run_id="run-1", session_id="42", user_id=7)

    assert config["configurable"]["thread_id"] == "chat:42"
    assert config["configurable"]["checkpoint_ns"] == "agent-runtime"


def test_memory_preserves_recent_order_and_character_limit() -> None:
    history = [
        ConversationMessage(role="user", content="1111"),
        ConversationMessage(role="assistant", content="2222"),
        ConversationMessage(role="user", content="3333"),
    ]
    memory = InMemoryMemory(history, history_limit=2, character_limit=5)
    assert [item.content for item in memory.conversation()] == ["3333"]
