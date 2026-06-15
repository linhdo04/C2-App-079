"""Reasoner implementations for the ReAct loop."""

import asyncio
from collections.abc import Callable, Sequence
from typing import Any, cast

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from .prompts import REACT_PROMPT, SYSTEM_PROMPT
from .react import Action, Memory, Reasoner, ReasoningDecision, Tool

logger = structlog.get_logger(__name__)


class GeminiReasoner:
    """Gemini-backed reasoner using a provider-neutral interface."""

    def __init__(self, llm: Any, *, timeout_seconds: float) -> None:
        self._llm = llm
        self._structured_llm = cast(Any, llm).with_structured_output(ReasoningDecision)
        self._timeout_seconds = timeout_seconds

    async def decide(
        self,
        goal: str,
        memory: Memory,
        tools: Sequence[Tool],
    ) -> ReasoningDecision:
        tool_catalog = "\n".join(
            f"- {tool.name}: {tool.description}\n  input_schema={tool.schema()}"
            for tool in tools
        )
        conversation = (
            "\n".join(
                f"{message.role}: {message.content}"
                for message in memory.conversation()
            )
            or "(no conversation history)"
        )
        history = (
            "\n".join(step.model_dump_json() for step in memory.steps())
            or "(no previous steps)"
        )
        response = await asyncio.wait_for(
            self._structured_llm.ainvoke(
                [
                    SystemMessage(content=f"{SYSTEM_PROMPT}\n\n{REACT_PROMPT}"),
                    HumanMessage(
                        content=(
                            f"User goal:\n{goal}\n\n"
                            f"Recent conversation:\n{conversation}\n\n"
                            f"Available tools:\n{tool_catalog}\n\n"
                            f"Previous ReAct steps:\n{history}"
                        )
                    ),
                ]
            ),
            timeout=self._timeout_seconds,
        )
        if isinstance(response, ReasoningDecision):
            return response
        return ReasoningDecision.model_validate(response)

    async def finalize(self, goal: str, memory: Memory) -> str:
        history = "\n".join(step.model_dump_json() for step in memory.steps())
        response = await asyncio.wait_for(
            self._llm.ainvoke(
                [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(
                        content=(
                            f"User goal:\n{goal}\n\n"
                            f"ReAct steps:\n{history}\n\n"
                            "The iteration limit was reached. Provide the safest "
                            "useful final answer from available observations and "
                            "state any limitation."
                        )
                    ),
                ]
            ),
            timeout=self._timeout_seconds,
        )
        self._log_usage(response)
        return str(getattr(response, "content", response))

    @staticmethod
    def _log_usage(response: Any, *, run_id: str = "") -> None:
        usage = getattr(response, "usage_metadata", None)
        if usage:
            logger.info("agent_llm_usage", run_id=run_id, **dict(usage))


ToolSelector = Callable[[str], list[str]]


class HeuristicReasoner:
    """Deterministic fallback when the configured LLM is unavailable."""

    def __init__(self, select_tools: ToolSelector) -> None:
        self._select_tools = select_tools

    async def decide(
        self,
        goal: str,
        memory: Memory,
        tools: Sequence[Tool],
    ) -> ReasoningDecision:
        available = {tool.name for tool in tools}
        called = {
            step.action.tool for step in memory.steps() if step.action is not None
        }
        for tool_name in self._select_tools(goal):
            if tool_name in available and tool_name not in called:
                return ReasoningDecision(
                    thought=f"Use {tool_name} to collect relevant evidence.",
                    action=Action(
                        tool=tool_name,
                        input=self._tool_input(tool_name, goal),
                    ),
                )

        return ReasoningDecision(
            thought="Available observations are sufficient for a safe response.",
            is_done=True,
            final_answer=self._answer(goal, memory),
        )

    async def finalize(self, goal: str, memory: Memory) -> str:
        return self._answer(goal, memory)

    @staticmethod
    def _tool_input(tool_name: str, goal: str) -> dict[str, Any]:
        if tool_name == "telemetry":
            return {"limit": 50}
        if tool_name == "analysis":
            from .tools.analysis import extract_crop_input

            return extract_crop_input(goal)
        if tool_name == "calculator":
            return {"expression": goal}
        return {"query": goal}

    @staticmethod
    def _answer(goal: str, memory: Memory) -> str:
        observations = [
            f"- {step.action.tool}: {step.observation}"
            for step in memory.steps()
            if step.action is not None
        ]
        if observations:
            return "Kết quả thu thập được:\n" + "\n".join(observations)
        return f"Tôi chưa có đủ dữ liệu để trả lời an toàn. Yêu cầu đã nhận: {goal}"


class FallbackReasoner:
    """Use a secondary reasoner whenever the primary provider fails."""

    def __init__(self, primary: Reasoner, fallback: Reasoner) -> None:
        self._primary = primary
        self._fallback = fallback

    async def decide(
        self,
        goal: str,
        memory: Memory,
        tools: Sequence[Tool],
    ) -> ReasoningDecision:
        try:
            return await self._primary.decide(goal, memory, tools)
        except Exception as exc:
            logger.warning(
                "agent_provider_fallback",
                operation="decide",
                provider="gemini",
                error_type=type(exc).__name__,
            )
            return await self._fallback.decide(goal, memory, tools)

    async def finalize(self, goal: str, memory: Memory) -> str:
        try:
            return await self._primary.finalize(goal, memory)
        except Exception as exc:
            logger.warning(
                "agent_provider_fallback",
                operation="finalize",
                provider="gemini",
                error_type=type(exc).__name__,
            )
            return await self._fallback.finalize(goal, memory)


__all__ = [
    "FallbackReasoner",
    "GeminiReasoner",
    "HeuristicReasoner",
    "REACT_PROMPT",
]
