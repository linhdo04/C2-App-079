"""Composition root for the production ReAct agent."""

from core import settings

from .guardrails import build_default_guardrails
from .llm import llm
from .react import Agent, AgentLoop, DoneOrMaxIterations, Executor, ToolRegistry
from .reasoners import FallbackReasoner, GeminiReasoner, HeuristicReasoner
from .tools import (
    AnalysisTool,
    CalculatorTool,
    DocumentSearchTool,
    SearchTool,
    TelemetryTool,
)

TELEMETRY_KEYWORDS = ("nhiệt độ", "độ ẩm", "cảm biến", "telemetry", "môi trường")
ANALYSIS_KEYWORDS = ("diện tích", "năng suất", "sản lượng", "tấn/ha", "thu hoạch")
SEARCH_KEYWORDS = (
    "giá",
    "thị trường",
    "kỹ thuật",
    "sâu bệnh",
    "mới nhất",
    "phân bón",
    "giống",
)
DOCUMENT_KEYWORDS = ("tài liệu", "document", "hướng dẫn nội bộ")


def _route_intents(question: str) -> list[str]:
    normalized = question.casefold()
    result: list[str] = []
    if any(keyword in normalized for keyword in TELEMETRY_KEYWORDS):
        result.append("telemetry")
    if any(keyword in normalized for keyword in ANALYSIS_KEYWORDS):
        result.append("analysis")
    if any(keyword in normalized for keyword in SEARCH_KEYWORDS):
        result.append("search")
    if any(keyword in normalized for keyword in DOCUMENT_KEYWORDS):
        result.append("document_search")
    if not result and any(character.isdigit() for character in normalized):
        result.append("calculator")
    return result


def create_default_agent() -> Agent:
    guardrails = build_default_guardrails(settings)
    registry = ToolRegistry(
        [
            CalculatorTool(),
            DocumentSearchTool(settings.agent_document_root_list),
            SearchTool(),
            TelemetryTool(),
            AnalysisTool(),
        ]
    )
    reasoner = FallbackReasoner(
        GeminiReasoner(llm, timeout_seconds=settings.agent_llm_timeout_seconds),
        HeuristicReasoner(_route_intents),
    )
    return Agent(
        AgentLoop(
            reasoner=reasoner,
            executor=Executor(
                registry,
                timeout_seconds=settings.agent_tool_timeout_seconds,
                max_retries=settings.agent_tool_max_retries,
                backoff_seconds=settings.agent_tool_retry_backoff_seconds,
                guardrails=guardrails,
            ),
            termination_condition=DoneOrMaxIterations(),
            max_iterations=settings.agent_max_iterations,
            guardrails=guardrails,
        )
    )


__all__ = ["create_default_agent"]
