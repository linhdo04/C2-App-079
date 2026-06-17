"""Application-facing AI agent functions."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import suppress
from typing import Literal, TypedDict

from core import settings

from .factory import create_default_agent
from .react import AgentEvent, AgentLoopResult, ConversationMessage, InMemoryMemory

default_agent = create_default_agent()

StatusPhase = Literal["routing", "tool", "synthesis"]


class AgentStreamEvent(TypedDict, total=False):
    event: Literal["status", "token"]
    phase: StatusPhase
    tool: str
    message: str
    content: str


TOOL_STATUS_MESSAGES = {
    "calculator": "Đang tính toán...",
    "telemetry": "Đang phân tích nhiệt độ và độ ẩm...",
    "search": "Đang tìm kiếm...",
    "analysis": "Đang phân tích dữ liệu mùa vụ...",
}


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
    result = await default_agent.run(
        question,
        user_id=user_id,
        session_id=session_id,
        memory=_memory(history),
    )
    return result.final_response


async def stream_agent(
    question: str,
    user_id: int | None = None,
    *,
    session_id: str | None = None,
    history: Sequence[ConversationMessage] | None = None,
) -> AsyncIterator[AgentStreamEvent]:
    queue: asyncio.Queue[AgentStreamEvent | None] = asyncio.Queue()
    memory = _memory(history)

    async def on_event(event: AgentEvent) -> None:
        if event.type != "tool_started" or event.tool is None:
            return
        await queue.put(
            {
                "event": "status",
                "phase": "tool",
                "tool": event.tool,
                "message": TOOL_STATUS_MESSAGES.get(
                    event.tool, f"Đang chạy {event.tool}..."
                ),
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
            "message": "Đang phân tích yêu cầu...",
        }
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
        result = await task
    finally:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    yield {
        "event": "status",
        "phase": "synthesis",
        "message": "Đang tổng hợp câu trả lời...",
    }
    for start in range(0, len(result.final_response), 32):
        yield {
            "event": "token",
            "content": result.final_response[start : start + 32],
        }


__all__ = [
    "AgentStreamEvent",
    "default_agent",
    "run_agent",
    "stream_agent",
]
