"""Composition root for the production ReAct agent."""

from core import settings

from .guardrails import build_default_guardrails
from .llm import llm
from .react import Agent, AgentLoop, DoneOrMaxIterations, Executor, ToolRegistry
from .reasoners import (
    FallbackReasoner,
    LLMReasoner,
    LLMRoutedFallbackReasoner,
    LLMToolRouter,
)
from .tool_policy import SemanticToolPolicy
from .tools import (
    AnalysisTool,
    CalculatorTool,
    SearchTool,
    TelemetryTool,
)


def create_default_agent() -> Agent:
    guardrails = build_default_guardrails(settings)
    registry = ToolRegistry(
        [
            CalculatorTool(),
            SearchTool(),
            TelemetryTool(),
            AnalysisTool(),
        ]
    )
    reasoner = FallbackReasoner(
        LLMReasoner(
            llm,
            timeout_seconds=settings.agent_llm_timeout_seconds,
            max_retries=settings.agent_llm_max_retries,
            backoff_seconds=settings.agent_llm_retry_backoff_seconds,
        ),
        LLMRoutedFallbackReasoner(
            LLMToolRouter(
                llm,
                timeout_seconds=settings.agent_fallback_router_timeout_seconds,
                max_retries=settings.agent_llm_max_retries,
                backoff_seconds=settings.agent_llm_retry_backoff_seconds,
            )
        ),
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
            tool_policy=SemanticToolPolicy(
                llm,
                timeout_seconds=settings.agent_fallback_router_timeout_seconds,
                max_retries=settings.agent_llm_max_retries,
                backoff_seconds=settings.agent_llm_retry_backoff_seconds,
            ),
        )
    )


__all__ = ["create_default_agent"]
