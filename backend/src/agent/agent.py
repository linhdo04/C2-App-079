"""AI Agent for agricultural assistance."""

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from .graph import graph
from .tools import (
    analyze_crop_data,
    get_weather_forecast,
    query_crop_database,
    web_search,
)

logger = logging.getLogger(__name__)

tools = [web_search, query_crop_database, get_weather_forecast, analyze_crop_data]


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


__all__ = ["graph", "run_agent", "tools"]
