"""LangGraph workflow for agricultural AI agent."""

from typing import Any

from langgraph.graph import END, StateGraph

from .nodes import (
    execute_tools_node,
    route_intent_node,
    synthesize_answer_node,
)
from .state import AgentState


def create_graph() -> Any:
    """Tạo LangGraph workflow cho agent."""
    workflow: StateGraph[AgentState] = StateGraph(AgentState)

    # Định nghĩa các nodes
    workflow.add_node("route_intent", route_intent_node)
    workflow.add_node("execute_tools", execute_tools_node)
    workflow.add_node("synthesize_answer", synthesize_answer_node)

    # Định nghĩa edges
    workflow.set_entry_point("route_intent")
    workflow.add_edge("route_intent", "execute_tools")
    workflow.add_edge("execute_tools", "synthesize_answer")
    workflow.add_edge("synthesize_answer", END)

    return workflow.compile()


graph = create_graph()

__all__ = ["graph", "create_graph"]
