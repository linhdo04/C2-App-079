"""Agent nodes for LangGraph workflow."""

from langchain_core.messages import ToolMessage

from .state import AgentState
from .tools import (
    get_weather_forecast,
    query_crop_database,
    web_search,
)


async def web_search_node(state: AgentState) -> AgentState:
    """Node để tìm kiếm web."""
    messages = state["messages"]
    last_message = messages[-1] if messages else None
    query = last_message.content if last_message else ""

    result = web_search.invoke({"query": query})
    return {"messages": [ToolMessage(content=result, tool_call_id="web_search")]}


async def query_crop_database_node(state: AgentState) -> AgentState:
    """Node để query database."""
    messages = state["messages"]
    last_message = messages[-1] if messages else None
    query = last_message.content if last_message else ""

    result = await query_crop_database.ainvoke({"query": query})
    return {"messages": [ToolMessage(content=result, tool_call_id="database")]}


async def get_weather_forecast_node(state: AgentState) -> AgentState:
    """Node để lấy dự báo thời tiết."""
    messages = state["messages"]
    last_message = messages[-1] if messages else None
    location = last_message.content if last_message else "Hanoi"

    result = await get_weather_forecast.ainvoke({"location": location, "days": 7})
    return {"messages": [ToolMessage(content=result, tool_call_id="weather")]}


__all__ = [
    "web_search_node",
    "query_crop_database_node",
    "get_weather_forecast_node",
]
