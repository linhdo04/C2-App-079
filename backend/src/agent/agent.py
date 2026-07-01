"""Application-facing AI agent functions."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import suppress
from typing import Literal, TypedDict, cast

from core import settings

from .agent_messages import load_agent_messages
from .factory import create_default_agent
from .intent_router import IntentRouter
from .llm import llm
from .pre_router import pre_route
from .react import AgentEvent, AgentLoopResult, ConversationMessage, InMemoryMemory

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
    route = pre_route(question)
    if route is not None:
        return route.response

    memory = _memory(history)
    routed_answer = await _intent_router_answer(question, memory)
    if routed_answer is not None:
        return routed_answer

    result = await default_agent.run(
        question,
        user_id=user_id,
        session_id=session_id,
        memory=memory,
    )
    return result.final_response


async def stream_agent(
    question: str,
    user_id: int | None = None,
    *,
    session_id: str | None = None,
    history: Sequence[ConversationMessage] | None = None,
) -> AsyncIterator[AgentStreamEvent]:
    route = pre_route(question)
    if route is not None:
        yield {
            "event": "status",
            "phase": "synthesis",
            "message": AGENT_MESSAGES.status("synthesis"),
        }
        for start in range(0, len(route.response), 32):
            yield {
                "event": "token",
                "content": route.response[start : start + 32],
            }
        return

    memory = _memory(history)
    routed_answer = await _intent_router_answer(question, memory)
    if routed_answer is not None:
        async for event in _stream_text_response(routed_answer):
            yield event
        return

    if hasattr(default_agent, "stream"):
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


async def _intent_router_answer(
    question: str,
    memory: InMemoryMemory,
) -> str | None:
    if not settings.agent_intent_router_enabled:
        return None
    try:
        decision = await intent_router.route(question, memory)
    except Exception:
        return None
    if decision is None or decision.route == "full_agent":
        return None
    return decision.answer


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
