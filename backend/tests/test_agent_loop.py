"""Contract tests for the production ReAct loop."""

import asyncio
from collections.abc import Sequence
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
from agent.tools import TelemetryInput


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


def test_memory_preserves_recent_order_and_character_limit() -> None:
    history = [
        ConversationMessage(role="user", content="1111"),
        ConversationMessage(role="assistant", content="2222"),
        ConversationMessage(role="user", content="3333"),
    ]
    memory = InMemoryMemory(history, history_limit=2, character_limit=5)
    assert [item.content for item in memory.conversation()] == ["3333"]
