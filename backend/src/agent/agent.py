"""AI Agent for agricultural assistance."""

import logging
import time
from collections.abc import AsyncIterator
from typing import Any, Literal, TypedDict

import structlog
from langchain_core.messages import HumanMessage

from .graph import graph
from .nodes import execute_tools_node, route_intent_node, stream_synthesize_answer
from .state import AgentState
from .tools import (
    analyze_crop_data,
    get_weather_forecast,
    query_crop_database,
    web_search,
)

logger = logging.getLogger(__name__)
event_logger = structlog.get_logger(__name__)

tools = [web_search, query_crop_database, get_weather_forecast, analyze_crop_data]

StatusPhase = Literal["routing", "tool", "synthesis"]


class AgentStreamEvent(TypedDict, total=False):
    event: Literal["status", "token"]
    phase: StatusPhase
    tool: str
    message: str
    content: str


TOOL_STATUS_MESSAGES = {
    "database": "Đang truy vấn dữ liệu...",
    "weather": "Đang lấy dữ liệu thời tiết...",
    "search": "Đang tìm kiếm...",
    "analysis": "Đang phân tích dữ liệu mùa vụ...",
}


async def run_agent(question: str) -> str:
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


async def stream_agent(question: str) -> AsyncIterator[AgentStreamEvent]:
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

        state: AgentState = {
            "question": question,
            "messages": [HumanMessage(content=question)],
        }
        state.update(await route_intent_node(state))

        for intent in state.get("intents", []):
            message = TOOL_STATUS_MESSAGES.get(intent)
            if message is not None:
                yield {
                    "event": "status",
                    "phase": "tool",
                    "tool": intent,
                    "message": message,
                }

        state.update(await execute_tools_node(state))
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


__all__ = ["AgentStreamEvent", "graph", "run_agent", "stream_agent", "tools"]
