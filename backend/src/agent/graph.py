"""LangGraph workflow for agricultural AI agent."""

from typing import Any

from langgraph.graph import END, StateGraph

from .nodes import (
    execute_tools_node,
    route_intent_node,
    synthesize_answer_node,
)
from .state import AgentState


def create_tool_graph() -> Any:
    """Create the shared routing and tool-execution workflow."""
    workflow: StateGraph[AgentState] = StateGraph(AgentState)
    workflow.add_node("route_intent", route_intent_node)
    workflow.add_node("execute_tools", execute_tools_node)
    workflow.set_entry_point("route_intent")
    workflow.add_edge("route_intent", "execute_tools")
    workflow.add_edge("execute_tools", END)
    return workflow.compile()


def create_graph() -> Any:
    """Create the complete agent workflow."""
    workflow: StateGraph[AgentState] = StateGraph(AgentState)
    workflow.add_node("route_intent", route_intent_node)
    workflow.add_node("execute_tools", execute_tools_node)
    workflow.add_node("synthesize_answer", synthesize_answer_node)
    workflow.set_entry_point("route_intent")
    workflow.add_edge("route_intent", "execute_tools")
    workflow.add_edge("execute_tools", "synthesize_answer")
    workflow.add_edge("synthesize_answer", END)
    return workflow.compile()


tool_graph = create_tool_graph()
graph = create_graph()

__all__ = ["create_graph", "create_tool_graph", "graph", "tool_graph"]
