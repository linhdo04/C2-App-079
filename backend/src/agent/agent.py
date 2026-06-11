"""Application-facing AI agent functions."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any, Literal, TypedDict, cast

from core import settings

from .factory import create_default_agent
from .react import AgentEvent, ConversationMessage, InMemoryMemory

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
    "document_search": "Đang tìm trong tài liệu...",
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
    history: Sequence[ConversationMessage] | None = None,
) -> str:
    result = await default_agent.run(
        question,
        user_id=user_id,
        memory=_memory(history),
    )
    return result.final_response


async def stream_agent(
    question: str,
    user_id: int | None = None,
    *,
    history: Sequence[ConversationMessage] | None = None,
) -> AsyncIterator[AgentStreamEvent]:
    queue: asyncio.Queue[AgentStreamEvent] = asyncio.Queue()
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

    yield {
        "event": "status",
        "phase": "routing",
        "message": "Đang phân tích yêu cầu...",
    }
    task = asyncio.create_task(
        default_agent.run(
            question,
            user_id=user_id,
            memory=memory,
            on_event=on_event,
        )
    )
    while not task.done() or not queue.empty():
        try:
            yield await asyncio.wait_for(queue.get(), timeout=0.05)
        except TimeoutError:
            continue
    result = await task
    yield {
        "event": "status",
        "phase": "synthesis",
        "message": "Đang tổng hợp câu trả lời...",
    }
    loop = getattr(default_agent, "loop", None)
    reasoner = getattr(loop, "reasoner", None)
    stream_finalizer = getattr(reasoner, "stream_finalize", None)
    if callable(stream_finalizer):
        async for token in cast(Any, stream_finalizer)(
            question,
            memory,
            result.run_id,
        ):
            yield {"event": "token", "content": token}
        return

    # Fake reasoners can omit streaming while preserving the same SSE envelope.
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
