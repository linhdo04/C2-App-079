"""Reasoner implementations for the ReAct loop."""

import asyncio
from collections.abc import Callable, Sequence
from typing import Any, cast
from urllib.parse import urlparse

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from .prompts import REACT_PROMPT, SYSTEM_PROMPT
from .react import Action, Memory, Reasoner, ReasoningDecision, Tool
from .tracing import agent_span, langchain_config, update_observation

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
        messages = [
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
        span_metadata = {
            "operation": "decide",
            "timeout_seconds": self._timeout_seconds,
            "tool_count": len(tools),
        }
        with agent_span("agent-reasoner", metadata=span_metadata) as span:
            try:
                response = await asyncio.wait_for(
                    self._structured_llm.ainvoke(
                        messages,
                        config=langchain_config(
                            "reasoner-decide",
                            extra_metadata=span_metadata,
                        ),
                    ),
                    timeout=self._timeout_seconds,
                )
            except Exception as exc:
                update_observation(
                    span,
                    operation="agent-reasoner",
                    metadata={
                        **span_metadata,
                        "error_type": type(exc).__name__,
                        "timed_out": isinstance(exc, TimeoutError),
                    },
                    level="ERROR",
                    status_message=(
                        f"Reasoner decide failed with {type(exc).__name__}."
                    ),
                )
                raise
        if isinstance(response, ReasoningDecision):
            return response
        return ReasoningDecision.model_validate(response)

    async def finalize(self, goal: str, memory: Memory) -> str:
        history = "\n".join(step.model_dump_json() for step in memory.steps())
        messages = [
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
        span_metadata = {
            "operation": "finalize",
            "timeout_seconds": self._timeout_seconds,
        }
        with agent_span("agent-reasoner", metadata=span_metadata) as span:
            try:
                response = await asyncio.wait_for(
                    self._llm.ainvoke(
                        messages,
                        config=langchain_config(
                            "reasoner-finalize",
                            extra_metadata=span_metadata,
                        ),
                    ),
                    timeout=self._timeout_seconds,
                )
            except Exception as exc:
                update_observation(
                    span,
                    operation="agent-reasoner",
                    metadata={
                        **span_metadata,
                        "error_type": type(exc).__name__,
                        "timed_out": isinstance(exc, TimeoutError),
                    },
                    level="ERROR",
                    status_message=(
                        f"Reasoner finalize failed with {type(exc).__name__}."
                    ),
                )
                raise
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
        search_results = [
            result
            for step in memory.steps()
            if step.action is not None and step.action.tool == "search"
            for result in _parse_search_observation(step.observation)
        ]
        if search_results:
            return _format_search_fallback_answer(goal, search_results)

        observations = [
            f"- {step.action.tool}: {step.observation}"
            for step in memory.steps()
            if step.action is not None
        ]
        if observations:
            return "Kết quả thu thập được:\n" + "\n".join(observations)
        return f"Tôi chưa có đủ dữ liệu để trả lời an toàn. Yêu cầu đã nhận: {goal}"


def _parse_search_observation(observation: str) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for block in observation.split("\n\n"):
        result: dict[str, str] = {}
        current_key: str | None = None
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if line.startswith("- Title:"):
                result["title"] = line.removeprefix("- Title:").strip()
                current_key = "title"
            elif line.startswith("URL:"):
                result["url"] = line.removeprefix("URL:").strip()
                current_key = "url"
            elif line.startswith("Snippet:"):
                result["snippet"] = line.removeprefix("Snippet:").strip()
                current_key = "snippet"
            elif current_key is not None and line:
                result[current_key] = f"{result[current_key]} {line}".strip()
        if result.get("url"):
            results.append(result)
    return results


def _format_search_fallback_answer(
    goal: str,
    results: list[dict[str, str]],
    *,
    limit: int = 5,
) -> str:
    unique_results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for result in results:
        url = result["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        unique_results.append(result)
        if len(unique_results) >= limit:
            break

    bullets = []
    sources = []
    for index, result in enumerate(unique_results, start=1):
        snippet = _shorten(result.get("snippet", "").strip(), 260)
        title = result.get("title") or _source_label(result["url"])
        if snippet:
            bullets.append(f"- {snippet} [{index}]")
        else:
            bullets.append(f"- Có nguồn liên quan: {title} [{index}]")
        sources.append(f"{index}. [{title}]({result['url']})")

    return "\n\n".join(
        [
            "Tôi tìm thấy một số nguồn web liên quan. Bạn nên dùng các nguồn "
            "dưới đây để kiểm chứng trước khi áp dụng.",
            f"Yêu cầu: {goal}",
            "Thông tin nổi bật:\n" + "\n".join(bullets),
            "Nguồn tham khảo:\n" + "\n".join(sources),
        ]
    )


def _shorten(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3].rstrip() + "..."


def _source_label(url: str) -> str:
    host = urlparse(url).netloc.removeprefix("www.")
    return host or "Nguồn tham khảo"


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
