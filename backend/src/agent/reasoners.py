"""Reasoner implementations for the ReAct loop."""

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal, cast
from urllib.parse import urlparse

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .prompts import REACT_PROMPT, SYSTEM_PROMPT
from .react import Action, Memory, Reasoner, ReasoningDecision, Tool
from .tracing import agent_span, langchain_config, update_observation

logger = structlog.get_logger(__name__)

LLM_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
LLM_RETRYABLE_CODE_NAMES = {
    "RESOURCE_EXHAUSTED",
    "UNAVAILABLE",
    "DEADLINE_EXCEEDED",
    "INTERNAL",
}


class FallbackRouteDecision(BaseModel):
    """A narrow LLM routing decision used only after the primary reasoner fails."""

    tool: Literal["search", "telemetry", "analysis", "calculator", "none"]
    input: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1)


async def _ainvoke_llm_with_retry(
    invoke: Callable[[], Awaitable[Any]],
    *,
    operation: str,
    timeout_seconds: float,
    max_retries: int,
    backoff_seconds: float,
) -> Any:
    allowed_attempts = max_retries + 1
    for attempt in range(1, allowed_attempts + 1):
        try:
            return await asyncio.wait_for(invoke(), timeout=timeout_seconds)
        except Exception as exc:
            retryable = _is_retryable_llm_error(exc)
            should_retry = retryable and attempt < allowed_attempts
            logger.warning(
                "agent_llm_call_failed",
                operation=operation,
                attempt=attempt,
                will_retry=should_retry,
                error_type=type(exc).__name__,
                **_llm_error_metadata(exc),
            )
            if not should_retry:
                raise
            await asyncio.sleep(backoff_seconds * (2 ** (attempt - 1)))
    raise RuntimeError("LLM retry loop exited unexpectedly")


def _is_retryable_llm_error(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    status_code = _llm_status_code(exc)
    if status_code in LLM_RETRYABLE_STATUS_CODES:
        return True
    code = _llm_error_code(exc)
    if code is not None and code in LLM_RETRYABLE_CODE_NAMES:
        return True
    message = str(exc).casefold()
    return any(
        marker in message
        for marker in (
            "429",
            "rate limit",
            "resource exhausted",
            "quota",
            "temporarily unavailable",
            "service unavailable",
        )
    )


def _llm_error_metadata(exc: Exception) -> dict[str, Any]:
    metadata: dict[str, Any] = {"retryable": _is_retryable_llm_error(exc)}
    status_code = _llm_status_code(exc)
    if status_code is not None:
        metadata["status_code"] = status_code
    code = _llm_error_code(exc)
    if code is not None:
        metadata["provider_code"] = code
    return metadata


def _llm_status_code(exc: Exception) -> int | None:
    for candidate in (
        getattr(exc, "status_code", None),
        getattr(exc, "status", None),
        getattr(getattr(exc, "response", None), "status_code", None),
        getattr(getattr(exc, "response", None), "status", None),
    ):
        parsed = _parse_status_code(candidate)
        if parsed is not None:
            return parsed
    return None


def _parse_status_code(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _llm_error_code(exc: Exception) -> str | None:
    code = getattr(exc, "code", None)
    if callable(code):
        try:
            code = code()
        except Exception:
            return None
    if code is None:
        return None
    name = getattr(code, "name", None)
    if isinstance(name, str):
        return name
    return str(code).rsplit(".", maxsplit=1)[-1]


class GeminiReasoner:
    """Gemini-backed reasoner using a provider-neutral interface."""

    def __init__(
        self,
        llm: Any,
        *,
        timeout_seconds: float,
        max_retries: int = 0,
        backoff_seconds: float = 0.5,
    ) -> None:
        self._llm = llm
        self._structured_llm = cast(Any, llm).bind(
            response_mime_type="application/json",
            response_schema=ReasoningDecision.model_json_schema(),
        )
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

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
                response = await _ainvoke_llm_with_retry(
                    lambda: self._structured_llm.ainvoke(
                        messages,
                        config=langchain_config(
                            "reasoner-decide",
                            extra_metadata=span_metadata,
                        ),
                    ),
                    operation="reasoner-decide",
                    timeout_seconds=self._timeout_seconds,
                    max_retries=self._max_retries,
                    backoff_seconds=self._backoff_seconds,
                )
            except Exception as exc:
                update_observation(
                    span,
                    operation="agent-reasoner",
                    metadata={
                        **span_metadata,
                        "error_type": type(exc).__name__,
                        "timed_out": isinstance(exc, TimeoutError),
                        **_llm_error_metadata(exc),
                    },
                    level="ERROR",
                    status_message=(
                        f"Reasoner decide failed with {type(exc).__name__}."
                    ),
                )
                raise
        return _parse_reasoning_decision(response)

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
                response = await _ainvoke_llm_with_retry(
                    lambda: self._llm.ainvoke(
                        messages,
                        config=langchain_config(
                            "reasoner-finalize",
                            extra_metadata=span_metadata,
                        ),
                    ),
                    operation="reasoner-finalize",
                    timeout_seconds=self._timeout_seconds,
                    max_retries=self._max_retries,
                    backoff_seconds=self._backoff_seconds,
                )
            except Exception as exc:
                update_observation(
                    span,
                    operation="agent-reasoner",
                    metadata={
                        **span_metadata,
                        "error_type": type(exc).__name__,
                        "timed_out": isinstance(exc, TimeoutError),
                        **_llm_error_metadata(exc),
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


class LLMToolRouter:
    """Small structured router for fallback tool selection only."""

    def __init__(
        self,
        llm: Any,
        *,
        timeout_seconds: float,
        max_retries: int = 0,
        backoff_seconds: float = 0.5,
    ) -> None:
        self._structured_llm = cast(Any, llm).bind(
            response_mime_type="application/json",
            response_schema=FallbackRouteDecision.model_json_schema(),
        )
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    async def route(
        self,
        goal: str,
        memory: Memory,
        tools: Sequence[Tool],
    ) -> FallbackRouteDecision:
        tool_catalog = "\n".join(
            f"- {tool.name}: {tool.description}\n  input_schema={tool.schema()}"
            for tool in tools
        )
        history = (
            "\n".join(step.model_dump_json() for step in memory.steps())
            or "(no previous steps)"
        )
        messages = [
            SystemMessage(
                content=(
                    "You are a fallback tool router. Select one available tool "
                    "that should gather evidence for the user goal. Do not answer "
                    "the user. Use only the provided tool names and input schemas. "
                    "Return tool='none' only when no tool can help."
                )
            ),
            HumanMessage(
                content=(
                    f"User goal:\n{goal}\n\n"
                    f"Available tools:\n{tool_catalog}\n\n"
                    f"Previous ReAct steps:\n{history}"
                )
            ),
        ]
        response = await _ainvoke_llm_with_retry(
            lambda: self._structured_llm.ainvoke(
                messages,
                config=langchain_config(
                    "fallback-tool-router",
                    extra_metadata={"timeout_seconds": self._timeout_seconds},
                ),
            ),
            operation="fallback-tool-router",
            timeout_seconds=self._timeout_seconds,
            max_retries=self._max_retries,
            backoff_seconds=self._backoff_seconds,
        )
        return _parse_fallback_route_decision(response)


class LLMRoutedFallbackReasoner:
    """Fallback reasoner that asks an LLM router before using generic search."""

    def __init__(self, router: LLMToolRouter | None) -> None:
        self._router = router

    async def decide(
        self,
        goal: str,
        memory: Memory,
        tools: Sequence[Tool],
    ) -> ReasoningDecision:
        if _has_tool_observations(memory):
            return ReasoningDecision(
                thought="Available observations are sufficient for a safe response.",
                is_done=True,
                final_answer=self._answer(goal, memory),
            )

        if self._router is not None:
            try:
                routed = await self._router.route(goal, memory, tools)
                action = _action_from_route(routed, tools, memory)
                if action is not None:
                    return ReasoningDecision(
                        thought=f"Use {action.tool} from fallback router.",
                        action=action,
                    )
            except Exception as exc:
                logger.warning(
                    "agent_fallback_router_failed",
                    error_type=type(exc).__name__,
                    **_llm_error_metadata(exc),
                )

        action = _default_search_action(goal, tools, memory)
        if action is not None:
            return ReasoningDecision(
                thought="Use search as the generic fallback evidence source.",
                action=action,
            )

        return ReasoningDecision(
            thought="No fallback tool is available.",
            is_done=True,
            final_answer=self._answer(goal, memory),
        )

    async def finalize(self, goal: str, memory: Memory) -> str:
        return self._answer(goal, memory)

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
        return (
            "Không thể thu thập dữ liệu vì reasoner chính và fallback router "
            "không khả dụng, đồng thời không có tool dự phòng phù hợp."
        )


def _has_tool_observations(memory: Memory) -> bool:
    return any(step.action is not None for step in memory.steps())


def _action_from_route(
    decision: FallbackRouteDecision,
    tools: Sequence[Tool],
    memory: Memory,
) -> Action | None:
    if decision.tool == "none":
        return None
    tool_by_name = {tool.name: tool for tool in tools}
    tool = tool_by_name.get(decision.tool)
    if tool is None:
        return None
    try:
        validated_input = tool.input_model.model_validate(decision.input)
    except Exception:
        return None
    action = Action(
        tool=tool.name,
        input=validated_input.model_dump(mode="json"),
    )
    return None if _was_action_called(action, memory) else action


def _default_search_action(
    goal: str,
    tools: Sequence[Tool],
    memory: Memory,
) -> Action | None:
    search = next((tool for tool in tools if tool.name == "search"), None)
    if search is None:
        return None
    try:
        validated_input = search.input_model.model_validate(
            {"query": goal, "max_results": 5}
        )
    except Exception:
        return None
    action = Action(
        tool="search",
        input=validated_input.model_dump(mode="json"),
    )
    return None if _was_action_called(action, memory) else action


def _was_action_called(action: Action, memory: Memory) -> bool:
    call_key = f"{action.tool}:{json.dumps(action.input, sort_keys=True)}"
    return any(
        step.action is not None
        and f"{step.action.tool}:{json.dumps(step.action.input, sort_keys=True)}"
        == call_key
        for step in memory.steps()
    )


def _parse_fallback_route_decision(response: Any) -> FallbackRouteDecision:
    if isinstance(response, FallbackRouteDecision):
        return response
    if isinstance(response, dict):
        parsed = response.get("parsed")
        if parsed is not None:
            return _parse_fallback_route_decision(parsed)
        if response.get("parsing_error") is not None and "raw" in response:
            return _parse_fallback_route_decision(response["raw"])
        return FallbackRouteDecision.model_validate(response)
    content = _extract_message_content(response)
    if isinstance(content, str):
        return FallbackRouteDecision.model_validate_json(content)
    return FallbackRouteDecision.model_validate(content)


def _parse_reasoning_decision(response: Any) -> ReasoningDecision:
    if isinstance(response, ReasoningDecision):
        return response

    if isinstance(response, dict):
        parsed = response.get("parsed")
        if parsed is not None:
            return _parse_reasoning_decision(parsed)
        if response.get("parsing_error") is not None and "raw" in response:
            recovered = _recover_reasoning_decision(response["raw"])
            if recovered is not None:
                return recovered
        if {"thought", "action", "is_done", "final_answer"} & response.keys():
            return ReasoningDecision.model_validate(response)

    recovered = _recover_reasoning_decision(response)
    if recovered is not None:
        return recovered
    return ReasoningDecision.model_validate(response)


def _recover_reasoning_decision(raw: Any) -> ReasoningDecision | None:
    content = _extract_message_content(raw)
    for candidate in _json_candidates(content):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            payload = _decode_json_object(candidate)
            if payload is None:
                continue
        try:
            return ReasoningDecision.model_validate(payload)
        except Exception:
            continue
    return None


def _extract_message_content(raw: Any) -> Any:
    if hasattr(raw, "content"):
        return getattr(raw, "content")
    if isinstance(raw, dict) and "content" in raw:
        return raw["content"]
    return raw


def _json_candidates(content: Any) -> list[str]:
    if isinstance(content, list):
        candidates: list[str] = []
        for item in reversed(content):
            candidates.extend(_json_candidates(item))
        return candidates
    if isinstance(content, dict):
        text = content.get("text") or content.get("content")
        return _json_candidates(text) if text is not None else []
    if not isinstance(content, str):
        return []

    candidates = [content.strip()]
    decoder = json.JSONDecoder()
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            _, end = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        candidates.append(content[index : index + end])
    return candidates


def _decode_json_object(value: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, character in enumerate(value):
        if character != "{":
            continue
        try:
            decoded, _ = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            return decoded
    return None


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
    "FallbackRouteDecision",
    "FallbackReasoner",
    "GeminiReasoner",
    "LLMRoutedFallbackReasoner",
    "LLMToolRouter",
    "REACT_PROMPT",
]
