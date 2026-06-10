"""AI Agent for agricultural assistance."""

import logging
import time
from collections.abc import AsyncIterator
from typing import Any, Literal, TypedDict, cast

import structlog
from langchain_core.messages import HumanMessage

from .graph import graph, tool_graph
from .nodes import stream_synthesize_answer
from .state import AgentState

logger = logging.getLogger(__name__)
event_logger = structlog.get_logger(__name__)

StatusPhase = Literal["routing", "tool", "synthesis"]


class AgentStreamEvent(TypedDict, total=False):
    event: Literal["status", "token"]
    phase: StatusPhase
    tool: str
    message: str
    content: str


TOOL_STATUS_MESSAGES = {
    "telemetry": "Đang phân tích nhiệt độ và độ ẩm...",
    "search": "Đang tìm kiếm...",
    "analysis": "Đang phân tích dữ liệu mùa vụ...",
}


async def run_agent(question: str, user_id: int | None = None) -> str:
    """Run the agent with the provided question and return a string answer.

    Args:
        question: Câu hỏi của người dùng

    Returns:
        Câu trả lời từ agent
    """
    try:
        # Tạo initial state với question gốc và message từ user
        initial_state: dict[str, Any] = {
            "question": question,
            "messages": [HumanMessage(content=question)],
        }
        if user_id is not None:
            initial_state["user_id"] = user_id

        # Invoke graph với state
        result = await graph.ainvoke(initial_state)

        answer = result.get("answer")
        if answer:
            return str(answer)

        # Fallback cho state cũ hoặc graph không tạo answer
        messages = result.get("messages", [])
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, "content"):
                return str(last_message.content)
            return "Không có câu trả lời"

        return "Không có câu trả lời"

    except Exception:
        logger.exception("Agent run failed")
        raise


async def stream_agent(
    question: str,
    user_id: int | None = None,
) -> AsyncIterator[AgentStreamEvent]:
    """Stream high-level progress and the synthesized answer."""
    started_at = time.perf_counter()
    try:
        event_logger.info(
            "agent_stream_started",
        )
        yield {
            "event": "status",
            "phase": "routing",
            "message": "Đang phân tích yêu cầu...",
        }

        initial_state: AgentState = {
            "question": question,
            "messages": [HumanMessage(content=question)],
        }
        if user_id is not None:
            initial_state["user_id"] = user_id
        state = cast(AgentState, dict(initial_state))
        async for update in tool_graph.astream(initial_state, stream_mode="updates"):
            route_update = update.get("route_intent")
            if route_update is not None:
                state.update(route_update)
                for intent in route_update.get("intents", []):
                    message = TOOL_STATUS_MESSAGES.get(intent)
                    if message is not None:
                        yield {
                            "event": "status",
                            "phase": "tool",
                            "tool": intent,
                            "message": message,
                        }

            tool_update = update.get("execute_tools")
            if tool_update is not None:
                state.update(tool_update)

        yield {
            "event": "status",
            "phase": "synthesis",
            "message": "Đang tổng hợp câu trả lời...",
        }

        first_token_logged = False
        async for token in stream_synthesize_answer(state):
            if not first_token_logged:
                first_token_logged = True
                event_logger.info(
                    "agent_stream_first_token",
                    duration_ms=round(
                        (time.perf_counter() - started_at) * 1000,
                        2,
                    ),
                )
            yield {"event": "token", "content": token}
    finally:
        event_logger.info(
            "agent_stream_completed",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )


__all__ = ["AgentStreamEvent", "graph", "run_agent", "stream_agent"]
