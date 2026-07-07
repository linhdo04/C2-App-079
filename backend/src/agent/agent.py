"""Application-facing AI agent functions."""

import asyncio
import time
from collections.abc import AsyncIterator, Sequence
from contextlib import suppress
from typing import Literal, TypedDict, cast

import structlog

from core import settings

from .agent_messages import load_agent_messages
from .factory import create_default_agent
from .intent_router import IntentRouter
from .llm import llm
from .pre_router import pre_route
from .react import AgentEvent, AgentLoopResult, ConversationMessage, InMemoryMemory
from .tracing import (
    agent_run_observation,
    agent_span,
    agent_trace_scope,
    current_trace_context,
    update_observation,
)

default_agent = create_default_agent()
intent_router = IntentRouter(
    llm,
    timeout_seconds=settings.agent_intent_router_timeout_seconds,
    min_confidence=settings.agent_intent_router_min_confidence,
    max_retries=0,
    backoff_seconds=settings.agent_llm_retry_backoff_seconds,
)

StatusPhase = Literal["routing", "tool", "synthesis"]


class AgentStreamEvent(TypedDict, total=False):
    event: Literal["status", "token"]
    phase: StatusPhase
    tool: str
    message: str
    content: str


AGENT_MESSAGES = load_agent_messages()
logger = structlog.get_logger(__name__)


def _memory(history: Sequence[ConversationMessage] | None) -> InMemoryMemory:
    return InMemoryMemory(
        history or (),
        history_limit=settings.agent_memory_max_messages,
        character_limit=settings.agent_memory_max_characters,
    )


async def run_agent(
    question: str,
    user_id: int | None = None,
    *,
    session_id: str | None = None,
    history: Sequence[ConversationMessage] | None = None,
) -> str:
    started_at = time.perf_counter()
    with agent_trace_scope(user_id=user_id, session_id=session_id) as (context, owned):
        observation_manager = (
            agent_run_observation(context, question=question)
            if owned
            else agent_span("agent-facade", metadata={"streamed": False})
        )
        with observation_manager as observation:
            try:
                with agent_span("agent-pre-router") as span:
                    route = pre_route(question)
                    update_observation(
                        span,
                        metadata={
                            "matched": route is not None,
                            "route": route.kind if route is not None else "full_agent",
                        },
                    )
                if route is not None:
                    _complete_facade_observation(
                        observation, started_at, route="pre_router", success=True
                    )
                    return route.response

                memory = _observed_memory(history)
                routed_answer = await _intent_router_answer(question, memory)
                if routed_answer is not None:
                    _complete_facade_observation(
                        observation, started_at, route="intent_router", success=True
                    )
                    return routed_answer

                with agent_span("agent-runtime-dispatch") as span:
                    result = await default_agent.run(
                        question,
                        user_id=user_id,
                        session_id=session_id,
                        memory=memory,
                    )
                    update_observation(
                        span,
                        metadata={
                            "success": result.done,
                            "iterations": result.iterations,
                            "termination_reason": result.termination_reason,
                        },
                    )
                _complete_facade_observation(
                    observation,
                    started_at,
                    route="full_agent",
                    success=result.done,
                )
                return result.final_response
            except Exception as exc:
                _complete_facade_observation(
                    observation,
                    started_at,
                    route="error",
                    success=False,
                    error_type=type(exc).__name__,
                )
                raise


async def stream_agent(
    question: str,
    user_id: int | None = None,
    *,
    session_id: str | None = None,
    history: Sequence[ConversationMessage] | None = None,
) -> AsyncIterator[AgentStreamEvent]:
    started_at = time.perf_counter()
    with agent_trace_scope(user_id=user_id, session_id=session_id) as (context, owned):
        observation_manager = (
            agent_run_observation(context, question=question, streamed=True)
            if owned
            else agent_span("agent-facade", metadata={"streamed": True})
        )
        with observation_manager as observation:
            try:
                async for event in _stream_agent_observed(
                    question,
                    user_id=user_id,
                    session_id=session_id,
                    history=history,
                    observation=observation,
                    started_at=started_at,
                ):
                    yield event
            except (GeneratorExit, asyncio.CancelledError):
                _complete_facade_observation(
                    observation,
                    started_at,
                    route="cancelled",
                    success=False,
                    error_type="CancelledError",
                )
                raise
            except Exception as exc:
                _complete_facade_observation(
                    observation,
                    started_at,
                    route="error",
                    success=False,
                    error_type=type(exc).__name__,
                )
                raise


async def _stream_agent_observed(
    question: str,
    *,
    user_id: int | None,
    session_id: str | None,
    history: Sequence[ConversationMessage] | None,
    observation: object,
    started_at: float,
) -> AsyncIterator[AgentStreamEvent]:
    with agent_span("agent-pre-router") as span:
        route = pre_route(question)
        update_observation(
            span,
            metadata={
                "matched": route is not None,
                "route": route.kind if route is not None else "full_agent",
            },
        )
    if route is not None:
        async for event in _stream_text_response(route.response):
            yield event
        _complete_facade_observation(
            observation, started_at, route="pre_router", success=True
        )
        return

    memory = _observed_memory(history)
    routed_answer = await _intent_router_answer(question, memory)
    if routed_answer is not None:
        async for event in _stream_text_response(routed_answer):
            yield event
        _complete_facade_observation(
            observation, started_at, route="intent_router", success=True
        )
        return

    if hasattr(default_agent, "stream"):
        with agent_span("agent-runtime-dispatch", metadata={"streamed": True}):
            async for stream_event in default_agent.stream(
                question,
                user_id=user_id,
                session_id=session_id,
                memory=memory,
            ):
                if stream_event.get("event") == "result":
                    continue
                if stream_event.get("event") == "status":
                    if stream_event.get("phase") == "tool" and stream_event.get("tool"):
                        tool = str(stream_event["tool"])
                        stream_event = {
                            **stream_event,
                            "message": AGENT_MESSAGES.tool(tool),
                        }
                    yield cast(AgentStreamEvent, stream_event)
                elif stream_event.get("event") == "token":
                    yield cast(AgentStreamEvent, stream_event)
        _complete_facade_observation(
            observation, started_at, route="full_agent", success=True
        )
        return

    # Compatibility path for tests or custom agent doubles that only implement run().
    queue: asyncio.Queue[AgentStreamEvent | None] = asyncio.Queue()

    async def on_event(event: AgentEvent) -> None:
        if event.type != "tool_started" or event.tool is None:
            return
        await queue.put(
            {
                "event": "status",
                "phase": "tool",
                "tool": event.tool,
                "message": AGENT_MESSAGES.tool(event.tool),
            }
        )

    async def run_with_completion_signal() -> AgentLoopResult:
        try:
            return await default_agent.run(
                question,
                user_id=user_id,
                session_id=session_id,
                memory=memory,
                on_event=on_event,
            )
        finally:
            await queue.put(None)

    task = asyncio.create_task(run_with_completion_signal())
    try:
        yield {
            "event": "status",
            "phase": "routing",
            "message": AGENT_MESSAGES.status("routing_analyzing"),
        }
        while True:
            queued_event = await queue.get()
            if queued_event is None:
                break
            yield queued_event
        result = await task
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    yield {
        "event": "status",
        "phase": "synthesis",
        "message": AGENT_MESSAGES.status("synthesis"),
    }
    for start in range(0, len(result.final_response), 32):
        yield {
            "event": "token",
            "content": result.final_response[start : start + 32],
        }
    _complete_facade_observation(
        observation, started_at, route="full_agent_compat", success=result.done
    )


async def _intent_router_answer(
    question: str,
    memory: InMemoryMemory,
) -> str | None:
    if not settings.agent_intent_router_enabled:
        return None
    with agent_span("agent-intent-router") as span:
        try:
            decision = await intent_router.route(question, memory)
        except Exception as exc:
            update_observation(
                span,
                metadata={"outcome": "fallback", "error_type": type(exc).__name__},
                level="ERROR",
            )
            return None
        update_observation(
            span,
            metadata={
                "outcome": decision.route if decision is not None else "low_confidence",
                "confidence": decision.confidence if decision is not None else None,
            },
        )
        if decision is None or decision.route == "full_agent":
            return None
        return decision.answer


def _observed_memory(
    history: Sequence[ConversationMessage] | None,
) -> InMemoryMemory:
    with agent_span(
        "agent-memory",
        metadata={
            "history_messages": len(history or ()),
            "history_characters": sum(len(item.content) for item in history or ()),
        },
    ) as span:
        memory = _memory(history)
        update_observation(
            span,
            metadata={"retained_messages": len(memory.conversation())},
        )
        return memory


def _complete_facade_observation(
    observation: object,
    started_at: float,
    *,
    route: str,
    success: bool,
    error_type: str | None = None,
) -> None:
    metadata: dict[str, object] = {
        "route": route,
        "success": success,
        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
    }
    context = current_trace_context()
    if context is not None:
        metadata["run_id"] = context.run_id
    if error_type is not None:
        metadata["error_type"] = error_type
    update_observation(
        observation,
        operation="agent-run",
        metadata=metadata,
        level="ERROR" if error_type is not None else None,
    )
    logger.info("agent_facade_summary", **metadata)


async def _stream_text_response(content: str) -> AsyncIterator[AgentStreamEvent]:
    yield {
        "event": "status",
        "phase": "synthesis",
        "message": AGENT_MESSAGES.status("synthesis"),
    }
    for start in range(0, len(content), 32):
        yield {
            "event": "token",
            "content": content[start : start + 32],
        }


__all__ = [
    "AgentStreamEvent",
    "default_agent",
    "run_agent",
    "stream_agent",
]
