"""Core abstractions for the production ReAct agent loop."""

import asyncio
import inspect
import json
import re
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import structlog
from pydantic import BaseModel, Field, ValidationError, model_validator

from .guardrails import GuardrailPipeline
from .tracing import (
    AgentTraceContext,
    agent_run_observation,
    agent_span,
    reset_trace_context,
    set_trace_context,
    update_observation,
)

logger = structlog.get_logger(__name__)

TerminationReason = Literal[
    "done",
    "max_iterations",
    "no_progress",
    "reasoner_error",
    "guardrail_blocked",
]


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class Action(BaseModel):
    """A single schema-based tool call selected by the reasoner."""

    tool: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)


class ReasoningDecision(BaseModel):
    thought: str = Field(min_length=1)
    action: Action | None = None
    is_done: bool = False
    final_answer: str | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> "ReasoningDecision":
        if self.is_done and not self.final_answer:
            raise ValueError("A completed decision requires final_answer")
        if not self.is_done and self.action is None:
            raise ValueError("An incomplete decision requires an action")
        return self


class ReActStep(BaseModel):
    thought: str
    action: Action | None
    observation: str
    is_done: bool = False


@dataclass(frozen=True)
class ToolContext:
    goal: str
    user_id: int | None = None
    run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class EmptyToolInput(BaseModel):
    pass


class Tool(ABC):
    name: str
    description: str
    input_model: type[BaseModel] = EmptyToolInput
    idempotent: bool = True
    retryable: bool = False

    @abstractmethod
    async def execute(self, tool_input: BaseModel, context: ToolContext) -> str:
        """Execute validated input and return an observation."""

    def schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()


ToolHandler = Callable[[BaseModel, ToolContext], Awaitable[str]]


class CallableTool(Tool):
    def __init__(
        self,
        name: str,
        description: str,
        handler: ToolHandler,
        *,
        input_model: type[BaseModel] = EmptyToolInput,
        idempotent: bool = True,
        retryable: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self.input_model = input_model
        self.idempotent = idempotent
        self.retryable = retryable
        self._handler = handler

    async def execute(self, tool_input: BaseModel, context: ToolContext) -> str:
        return await self._handler(tool_input, context)


class ToolRegistry:
    def __init__(self, tools: Sequence[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> tuple[Tool, ...]:
        return tuple(self._tools.values())


class Memory(Protocol):
    def add(self, step: ReActStep) -> None: ...

    def steps(self) -> tuple[ReActStep, ...]: ...

    def conversation(self) -> tuple[ConversationMessage, ...]: ...


class InMemoryMemory:
    def __init__(
        self,
        history: Sequence[ConversationMessage] = (),
        *,
        history_limit: int = 10,
        character_limit: int = 12_000,
    ) -> None:
        recent = list(history[-history_limit:])
        while recent and sum(len(item.content) for item in recent) > character_limit:
            recent.pop(0)
        self._history = tuple(recent)
        self._steps: list[ReActStep] = []

    def add(self, step: ReActStep) -> None:
        self._steps.append(step)

    def steps(self) -> tuple[ReActStep, ...]:
        return tuple(self._steps)

    def conversation(self) -> tuple[ConversationMessage, ...]:
        return self._history


class Reasoner(Protocol):
    async def decide(
        self, goal: str, memory: Memory, tools: Sequence[Tool]
    ) -> ReasoningDecision: ...

    async def finalize(self, goal: str, memory: Memory) -> str: ...


class ToolPolicy(Protocol):
    async def decide(
        self,
        goal: str,
        memory: Memory,
        tools: Sequence[Tool],
    ) -> Action | None: ...


def _was_action_called(action: Action, memory: Memory) -> bool:
    call_key = f"{action.tool}:{json.dumps(action.input, sort_keys=True)}"
    return any(
        step.action is not None
        and f"{step.action.tool}:{json.dumps(step.action.input, sort_keys=True)}"
        == call_key
        for step in memory.steps()
    )


_EXTERNAL_SEARCH_INTENT_PATTERN = re.compile(
    r"\b("
    r"search|web|internet|google|forecast|news|market|regulation|"
    r"tìm\s*kiếm|tra\s*cứu|trên\s*mạng|trên\s*web|internet|google|"
    r"dự\s*báo|thời\s*tiết|hiện\s*tại|tin\s*tức|thị\s*trường|"
    r"giá\s*(?:cả|thị\s*trường)?|quy\s*định|khuyến\s*cáo|cảnh\s*báo|"
    r"sâu\s*bệnh"
    r")\b",
    re.IGNORECASE,
)
_AMBIGUOUS_DAY_ONLY_PATTERN = re.compile(
    r"\bngày\s+(?:[1-9]|[12]\d|3[01])\b",
    re.IGNORECASE,
)
_COMPLETE_DATE_PATTERN = re.compile(
    r"("
    r"\bngày\s+(?:[1-9]|[12]\d|3[01])\s*(?:/|-|\.|tháng)\b|"
    r"\b(?:[1-9]|[12]\d|3[01])\s*(?:/|-|\.)\s*(?:[1-9]|1[0-2])\b"
    r")",
    re.IGNORECASE,
)
_TELEMETRY_NO_DATA_MARKERS = (
    "Không có dữ liệu nhiệt độ hoặc độ ẩm",
    "Không có dữ liệu nhiệt độ",
    "Không có dữ liệu độ ẩm",
)


def _has_explicit_external_search_intent(goal: str) -> bool:
    return _EXTERNAL_SEARCH_INTENT_PATTERN.search(goal) is not None


def _has_empty_telemetry_observation(memory: Memory) -> bool:
    return any(
        step.action is not None
        and step.action.tool == "telemetry"
        and any(marker in step.observation for marker in _TELEMETRY_NO_DATA_MARKERS)
        for step in memory.steps()
    )


def _has_ambiguous_day_only_date(goal: str) -> bool:
    return (
        _AMBIGUOUS_DAY_ONLY_PATTERN.search(goal) is not None
        and _COMPLETE_DATE_PATTERN.search(goal) is None
    )


def _should_skip_tool_policy_after_terminal_telemetry(
    goal: str,
    memory: Memory,
) -> bool:
    if _has_explicit_external_search_intent(goal):
        return False
    steps = memory.steps()
    if not steps:
        return False
    last_action = steps[-1].action
    return (
        last_action is not None
        and last_action.tool == "telemetry"
        and "query_kinds" in last_action.input
    )


def _has_point_telemetry_query(action: Action) -> bool:
    query_kinds = action.input.get("query_kinds")
    return isinstance(query_kinds, list) and any(
        query_kind in {"temperature_at", "humidity_at"} for query_kind in query_kinds
    )


def _decision_guard_response(
    goal: str,
    action: Action,
    memory: Memory,
) -> str | None:
    if (
        action.tool == "search"
        and _has_empty_telemetry_observation(memory)
        and not _has_explicit_external_search_intent(goal)
    ):
        return (
            "Không có dữ liệu nhiệt độ hoặc độ ẩm của bạn cho khoảng thời gian "
            "đã hỏi. Tôi sẽ không dùng kết quả tìm kiếm web để thay thế dữ liệu "
            "telemetry nội bộ khi bạn chưa yêu cầu nguồn bên ngoài. Bạn có thể "
            "chọn khoảng thời gian khác hoặc kiểm tra thiết bị đã gửi dữ liệu chưa."
        )
    if (
        action.tool == "telemetry"
        and _has_ambiguous_day_only_date(goal)
        and not _has_point_telemetry_query(action)
    ):
        return (
            "Bạn vui lòng cung cấp đầy đủ ngày, tháng và năm cho khoảng thời gian "
            "cần xem telemetry, ví dụ: 18/06/2026. Câu hỏi hiện chỉ nêu “ngày 18” "
            "nên tôi không tự suy đoán tháng/năm để tránh lấy sai dữ liệu."
        )
    return None


@dataclass(frozen=True)
class ToolExecutionResult:
    observation: str
    succeeded: bool
    attempts: int


AgentEventType = Literal["tool_started", "tool_completed", "tool_failed", "completed"]


@dataclass(frozen=True)
class AgentEvent:
    type: AgentEventType
    run_id: str
    iteration: int
    tool: str | None = None
    attempts: int = 0
    duration_ms: float = 0
    termination_reason: TerminationReason | None = None


EventCallback = Callable[[AgentEvent], Awaitable[None] | None]


def _retryable_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    return (
        isinstance(exc, (TimeoutError, ConnectionError, OSError)) or status_code == 429
    )


class Executor:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        timeout_seconds: float,
        max_retries: int = 1,
        backoff_seconds: float = 0.25,
        guardrails: GuardrailPipeline | None = None,
    ) -> None:
        if timeout_seconds <= 0 or backoff_seconds < 0:
            raise ValueError("Invalid executor timing configuration")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self.registry = registry
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.guardrails = guardrails

    async def execute(
        self,
        action: Action,
        context: ToolContext,
        *,
        iteration: int = 0,
        on_event: EventCallback | None = None,
    ) -> ToolExecutionResult:
        tool = self.registry.get(action.tool)
        if tool is None:
            return ToolExecutionResult(
                observation=f"Tool '{action.tool}' is not available.",
                succeeded=False,
                attempts=0,
            )
        try:
            validated_input = tool.input_model.model_validate(action.input)
        except ValidationError:
            return ToolExecutionResult(
                observation=f"Input for tool '{action.tool}' is invalid.",
                succeeded=False,
                attempts=0,
            )
        if self.guardrails is not None:
            decision = self.guardrails.check_tool_input(
                tool.name,
                validated_input.model_dump(mode="json"),
            )
            if decision.blocked:
                logger.warning(
                    "agent_guardrail_blocked",
                    run_id=context.run_id,
                    stage="tool_input",
                    tool=tool.name,
                    reason=decision.reason,
                )
                return ToolExecutionResult(
                    observation="Tool input blocked by safety guardrail.",
                    succeeded=False,
                    attempts=0,
                )
            validated_input = tool.input_model.model_validate_json(decision.content)

        await _emit(
            on_event,
            AgentEvent("tool_started", context.run_id, iteration, tool=tool.name),
        )
        allowed_attempts = (
            self.max_retries + 1 if tool.idempotent and tool.retryable else 1
        )
        started_at = time.perf_counter()
        for attempt in range(1, allowed_attempts + 1):
            span_metadata = {
                "tool": tool.name,
                "iteration": iteration,
                "attempt": attempt,
                "timeout_seconds": self.timeout_seconds,
            }
            try:
                with agent_span(
                    "agent-tool",
                    metadata=span_metadata,
                ) as span:
                    try:
                        observation = await asyncio.wait_for(
                            tool.execute(validated_input, context),
                            timeout=self.timeout_seconds,
                        )
                    except Exception as exc:
                        update_observation(
                            span,
                            operation="agent-tool",
                            metadata={
                                **span_metadata,
                                "error_type": type(exc).__name__,
                                "timed_out": isinstance(exc, TimeoutError),
                            },
                            level="ERROR",
                            status_message=(
                                f"Tool '{tool.name}' failed with {type(exc).__name__}."
                            ),
                        )
                        raise
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                logger.info(
                    "agent_tool_completed",
                    run_id=context.run_id,
                    iteration=iteration,
                    tool=tool.name,
                    attempts=attempt,
                    duration_ms=duration_ms,
                )
                await _emit(
                    on_event,
                    AgentEvent(
                        "tool_completed",
                        context.run_id,
                        iteration,
                        tool=tool.name,
                        attempts=attempt,
                        duration_ms=duration_ms,
                    ),
                )
                safe_observation = str(observation)
                if self.guardrails is not None:
                    output_decision = self.guardrails.check_tool_output(
                        tool.name,
                        safe_observation,
                    )
                    if output_decision.blocked:
                        logger.warning(
                            "agent_guardrail_blocked",
                            run_id=context.run_id,
                            stage="tool_output",
                            tool=tool.name,
                            reason=output_decision.reason,
                        )
                        safe_observation = "Tool output blocked by safety guardrail."
                    else:
                        safe_observation = output_decision.content
                return ToolExecutionResult(safe_observation, True, attempt)
            except Exception as exc:
                should_retry = _retryable_error(exc) and attempt < allowed_attempts
                logger.warning(
                    "agent_tool_attempt_failed",
                    run_id=context.run_id,
                    iteration=iteration,
                    tool=tool.name,
                    attempt=attempt,
                    error_type=type(exc).__name__,
                    retrying=should_retry,
                )
                if not should_retry:
                    break
                await asyncio.sleep(self.backoff_seconds * (2 ** (attempt - 1)))

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        await _emit(
            on_event,
            AgentEvent(
                "tool_failed",
                context.run_id,
                iteration,
                tool=tool.name,
                attempts=attempt,
                duration_ms=duration_ms,
            ),
        )
        return ToolExecutionResult(
            observation=f"Tool '{action.tool}' is temporarily unavailable.",
            succeeded=False,
            attempts=attempt,
        )


class TerminationCondition(Protocol):
    def should_stop(
        self, *, step: ReActStep, iteration: int, max_iterations: int
    ) -> bool: ...


class DoneOrMaxIterations:
    def should_stop(
        self, *, step: ReActStep, iteration: int, max_iterations: int
    ) -> bool:
        return step.is_done or iteration >= max_iterations


@dataclass(frozen=True)
class AgentLoopResult:
    final_response: str
    done: bool
    iterations: int
    steps: tuple[ReActStep, ...]
    termination_reason: TerminationReason
    run_id: str = ""


StepCallback = Callable[[int, ReActStep], Awaitable[None] | None]


async def _emit(callback: EventCallback | None, event: AgentEvent) -> None:
    if callback is None:
        return
    result = callback(event)
    if inspect.isawaitable(result):
        await result


class AgentLoop:
    def __init__(
        self,
        *,
        reasoner: Reasoner,
        executor: Executor,
        termination_condition: TerminationCondition,
        max_iterations: int = 6,
        guardrails: GuardrailPipeline | None = None,
        tool_policy: ToolPolicy | None = None,
    ) -> None:
        if max_iterations <= 0:
            raise ValueError("max_iterations must be positive")
        self.reasoner = reasoner
        self.executor = executor
        self.termination_condition = termination_condition
        self.max_iterations = max_iterations
        self.guardrails = guardrails
        self.tool_policy = tool_policy

    async def run(
        self,
        goal: str,
        *,
        user_id: int | None = None,
        session_id: str | None = None,
        memory: Memory | None = None,
        on_step: StepCallback | None = None,
        on_event: EventCallback | None = None,
    ) -> AgentLoopResult:
        run_id = str(uuid.uuid4())
        trace_context = AgentTraceContext(
            run_id=run_id,
            user_id=user_id,
            session_id=session_id,
        )
        trace_token = set_trace_context(trace_context)
        started_at = time.perf_counter()

        try:
            checked_goal = (
                self.guardrails.check_input(goal)
                if self.guardrails is not None
                else None
            )
            if checked_goal is not None and checked_goal.blocked:
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                logger.warning(
                    "agent_guardrail_blocked",
                    run_id=run_id,
                    stage="input",
                    reason=checked_goal.reason,
                )
                await _emit(
                    on_event,
                    AgentEvent(
                        "completed",
                        run_id,
                        0,
                        duration_ms=duration_ms,
                        termination_reason="guardrail_blocked",
                    ),
                )
                return AgentLoopResult(
                    final_response=checked_goal.content,
                    done=False,
                    iterations=0,
                    steps=(),
                    termination_reason="guardrail_blocked",
                    run_id=run_id,
                )

            safe_goal = checked_goal.content if checked_goal is not None else goal
            active_memory = memory or InMemoryMemory()
            context = ToolContext(goal=safe_goal, user_id=user_id, run_id=run_id)
            calls: set[str] = set()
            reason: TerminationReason = "max_iterations"
            done = False
            final_response = ""
            last_iteration = 0

            with agent_run_observation(
                trace_context, question=safe_goal
            ) as observation:
                for iteration in range(1, self.max_iterations + 1):
                    last_iteration = iteration
                    try:
                        tools = self.executor.registry.list()
                        policy_action = (
                            await self.tool_policy.decide(
                                safe_goal, active_memory, tools
                            )
                            if self.tool_policy is not None
                            and not _should_skip_tool_policy_after_terminal_telemetry(
                                safe_goal,
                                active_memory,
                            )
                            else None
                        )
                        if policy_action is not None:
                            decision = ReasoningDecision(
                                thought=(
                                    f"Policy selected {policy_action.tool}"
                                    " for required evidence."
                                ),
                                action=policy_action,
                            )
                        else:
                            decision = await self.reasoner.decide(
                                safe_goal, active_memory, tools
                            )
                    except Exception as exc:
                        logger.error(
                            "agent_reasoner_failed",
                            run_id=run_id,
                            iteration=iteration,
                            error_type=type(exc).__name__,
                        )
                        raise

                    if decision.is_done:
                        final_response = decision.final_answer or ""
                        step = ReActStep(
                            thought=decision.thought,
                            action=None,
                            observation=final_response,
                            is_done=True,
                        )
                        done = True
                        reason = "done"
                    else:
                        action = decision.action
                        if action is None:
                            reason = "reasoner_error"
                            break
                        guarded_response = _decision_guard_response(
                            safe_goal, action, active_memory
                        )
                        if guarded_response is not None:
                            final_response = guarded_response
                            step = ReActStep(
                                thought=decision.thought,
                                action=None,
                                observation=final_response,
                                is_done=True,
                            )
                            done = True
                            reason = "done"
                            logger.info(
                                "agent_decision_guarded",
                                run_id=run_id,
                                iteration=iteration,
                                tool=action.tool,
                            )
                            active_memory.add(step)
                            if on_step is not None:
                                callback_result = on_step(iteration, step)
                                if inspect.isawaitable(callback_result):
                                    await callback_result
                            break
                        call_key = (
                            f"{action.tool}:{json.dumps(action.input, sort_keys=True)}"
                        )
                        if call_key in calls:
                            reason = "no_progress"
                            break
                        calls.add(call_key)
                        execution = await self.executor.execute(
                            action,
                            context,
                            iteration=iteration,
                            on_event=on_event,
                        )
                        step = ReActStep(
                            thought=decision.thought,
                            action=action,
                            observation=execution.observation,
                        )

                    active_memory.add(step)
                    if on_step is not None:
                        callback_result = on_step(iteration, step)
                        if inspect.isawaitable(callback_result):
                            await callback_result
                    if done:
                        break

                if not final_response:
                    try:
                        final_response = await self.reasoner.finalize(
                            safe_goal, active_memory
                        )
                    except Exception:
                        final_response = "Tôi chưa thể hoàn tất yêu cầu vào lúc này."
                if self.guardrails is not None:
                    output_decision = self.guardrails.check_output(final_response)
                    if output_decision.blocked:
                        logger.warning(
                            "agent_guardrail_blocked",
                            run_id=run_id,
                            stage="output",
                            reason=output_decision.reason,
                        )
                        final_response = output_decision.content
                        reason = "guardrail_blocked"
                        done = False
                    else:
                        final_response = output_decision.content

                result = AgentLoopResult(
                    final_response=final_response,
                    done=done,
                    iterations=last_iteration,
                    steps=active_memory.steps(),
                    termination_reason=reason,
                    run_id=run_id,
                )
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                if observation is not None:
                    observation.update(
                        output={"response": result.final_response},
                        metadata={
                            "iterations": result.iterations,
                            "termination_reason": reason,
                            "success": done,
                            "duration_ms": duration_ms,
                        },
                    )
                logger.info(
                    "agent_run_summary",
                    run_id=run_id,
                    success=done,
                    duration_ms=duration_ms,
                    iterations=result.iterations,
                    termination_reason=reason,
                )
                await _emit(
                    on_event,
                    AgentEvent(
                        "completed",
                        run_id,
                        result.iterations,
                        duration_ms=duration_ms,
                        termination_reason=reason,
                    ),
                )
                return result
        finally:
            reset_trace_context(trace_token)


class Agent:
    def __init__(self, loop: AgentLoop) -> None:
        self.loop = loop

    async def run(
        self,
        goal: str,
        *,
        user_id: int | None = None,
        session_id: str | None = None,
        memory: Memory | None = None,
        on_step: StepCallback | None = None,
        on_event: EventCallback | None = None,
    ) -> AgentLoopResult:
        return await self.loop.run(
            goal,
            user_id=user_id,
            session_id=session_id,
            memory=memory,
            on_step=on_step,
            on_event=on_event,
        )


__all__ = [
    "Action",
    "Agent",
    "AgentEvent",
    "AgentLoop",
    "AgentLoopResult",
    "CallableTool",
    "ConversationMessage",
    "DoneOrMaxIterations",
    "EmptyToolInput",
    "Executor",
    "InMemoryMemory",
    "Memory",
    "ReActStep",
    "Reasoner",
    "ReasoningDecision",
    "TerminationReason",
    "Tool",
    "ToolContext",
    "ToolPolicy",
    "ToolRegistry",
    "_was_action_called",
]
