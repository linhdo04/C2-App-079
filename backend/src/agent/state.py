"""Agent state definition."""

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

AgentIntent = str


class AgentState(TypedDict, total=False):
    """State cho LangGraph agent workflow."""

    question: str
    messages: Annotated[list[BaseMessage], add_messages]
    intents: list[AgentIntent]
    tool_results: dict[str, str]
    tool_errors: dict[str, str]
    answer: str
