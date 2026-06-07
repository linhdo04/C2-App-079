"""AI Agent for agricultural assistance."""

import logging
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from core.config import settings

from .graph import graph
from .tools import get_weather_forecast, query_crop_database, web_search

logger = logging.getLogger(__name__)

# Initialize LLM
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", api_key=settings.gemini_api_key)

tools = [web_search, query_crop_database, get_weather_forecast]


async def run_agent(question: str) -> str:
    """Run the agent with the provided question and return a string answer.

    Args:
        question: Câu hỏi của người dùng

    Returns:
        Câu trả lời từ agent
    """
    try:
        # Tạo initial state với message từ user
        initial_state: dict[str, Any] = {"messages": [HumanMessage(content=question)]}

        # Invoke graph với state
        result = await graph.ainvoke(initial_state)

        # Lấy message cuối cùng từ kết quả
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
