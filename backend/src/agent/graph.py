"""LangGraph workflow for agricultural AI agent."""

from typing import Any

from langgraph.graph import END, StateGraph

from .nodes import (
    get_weather_forecast_node,
    query_crop_database_node,
    web_search_node,
)
from .state import AgentState


def create_graph() -> Any:
    """Tạo LangGraph workflow cho agent."""
    workflow: StateGraph[AgentState] = StateGraph(AgentState)

    # Định nghĩa các nodes
    workflow.add_node("search", web_search_node)
    workflow.add_node("database", query_crop_database_node)
    workflow.add_node("weather", get_weather_forecast_node)

    # Định nghĩa edges
    workflow.set_entry_point("database")
    workflow.add_edge("database", "search")
    workflow.add_edge("search", "weather")
    workflow.add_edge("weather", END)

    return workflow.compile()


graph = create_graph()

__all__ = ["graph", "create_graph"]
