"""Reasoner implementations for the ReAct loop."""

import asyncio
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlparse

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from .prompts import REACT_PROMPT, SYSTEM_PROMPT
from .react import Action, Memory, Reasoner, ReasoningDecision, Tool, _was_action_called
from .structured import bind_structured_output
from .tracing import agent_span, langchain_config, update_observation
from .usage import record_llm_usage

logger = structlog.get_logger(__name__)

LLM_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
LLM_RETRYABLE_CODE_NAMES = {
    "RESOURCE_EXHAUSTED",
    "UNAVAILABLE",
    "DEADLINE_EXCEEDED",
    "INTERNAL",
}

# Some providers embed the suggested retry delay in two places inside the 429 body:
#   "Please retry in 28.823862733s"       (human-readable message, float seconds)
#   'retryDelay': '28s'  or  "retryDelay": "28s"  (structured detail)
_RETRY_DELAY_PATTERNS = (
    re.compile(r"retry in (\d+(?:\.\d+)?)s", re.IGNORECASE),
    re.compile(r"""['"]retryDelay['"]\s*:\s*['"](\d+(?:\.\d+)?)s['"]"""),
)
_MAX_SERVER_RETRY_DELAY_SECONDS = 5.0
DEFAULT_FALLBACK_ROUTE_REASON = "No reason provided by fallback router."


"""Return the server-suggested retry delay (seconds) embedded in a 429 body, or None."""


def _extract_server_retry_delay(exc: Exception) -> float | None:
    text = str(exc)
    for pattern in _RETRY_DELAY_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                continue
    return None


class FallbackRouteDecision(BaseModel):
    """A narrow LLM routing decision used only after the primary reasoner fails."""

    tool: Literal["search", "telemetry", "analysis", "calculator", "none"]
    input: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default=DEFAULT_FALLBACK_ROUTE_REASON, min_length=1)

    @field_validator("reason", mode="before")
    @classmethod
    def default_blank_reason(cls, value: Any) -> Any:
        if value is None:
            return DEFAULT_FALLBACK_ROUTE_REASON
        if isinstance(value, str) and not value.strip():
            return DEFAULT_FALLBACK_ROUTE_REASON
        return value


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
            response = await asyncio.wait_for(invoke(), timeout=timeout_seconds)
            await record_llm_usage(response, operation=operation)
            return response
        except Exception as exc:
            retryable = _is_retryable_llm_error(exc)
            should_retry = retryable and attempt < allowed_attempts
            server_delay = _extract_server_retry_delay(exc)
            if should_retry:
                if server_delay is not None:
                    sleep_seconds: float = min(
                        server_delay,
                        timeout_seconds,
                        _MAX_SERVER_RETRY_DELAY_SECONDS,
                    )
                else:
                    sleep_seconds = backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "agent_llm_call_failed",
                operation=operation,
                attempt=attempt,
                will_retry=should_retry,
                sleep_seconds=sleep_seconds if should_retry else None,
                error_type=type(exc).__name__,
                **_llm_error_metadata(exc, server_delay=server_delay),
            )
            if not should_retry:
                raise
            await asyncio.sleep(sleep_seconds)


def _chunk_content(chunk: Any) -> str:
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


async def _astream_llm_with_retry(
    stream: Callable[[], AsyncIterator[Any]],
    *,
    operation: str,
    timeout_seconds: float,
    max_retries: int,
    backoff_seconds: float,
) -> AsyncIterator[Any]:
    allowed_attempts = max_retries + 1
    for attempt in range(1, allowed_attempts + 1):
        yielded = False
        try:
            async with asyncio.timeout(timeout_seconds):
                async for chunk in stream():
                    yielded = True
                    await record_llm_usage(chunk, operation=operation)
                    yield chunk
            return
        except Exception as exc:
            retryable = _is_retryable_llm_error(exc)
            should_retry = retryable and not yielded and attempt < allowed_attempts
            server_delay = _extract_server_retry_delay(exc)
            if should_retry:
                if server_delay is not None:
                    sleep_seconds: float = min(
                        server_delay,
                        timeout_seconds,
                        _MAX_SERVER_RETRY_DELAY_SECONDS,
                    )
                else:
                    sleep_seconds = backoff_seconds * (2 ** (attempt - 1))
            logger.warning(
                "agent_llm_stream_failed",
                operation=operation,
                attempt=attempt,
                yielded=yielded,
                will_retry=should_retry,
                sleep_seconds=sleep_seconds if should_retry else None,
                error_type=type(exc).__name__,
                **_llm_error_metadata(exc, server_delay=server_delay),
            )
            if not should_retry:
                raise
            await asyncio.sleep(sleep_seconds)


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
    return any(marker in message for marker in _LLM_RETRYABLE_MESSAGE_MARKERS)


def _llm_error_metadata(
    exc: Exception,
    *,
    server_delay: float | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"retryable": _is_retryable_llm_error(exc)}
    status_code = _llm_status_code(exc)
    if status_code is not None:
        metadata["status_code"] = status_code
    code = _llm_error_code(exc)
    if code is not None:
        metadata["provider_code"] = code
    message = _llm_provider_message(exc)
    if message is not None:
        metadata["provider_message"] = message
    # Use pre-computed value when available to avoid running the regex twice.
    delay = (
        server_delay if server_delay is not None else _extract_server_retry_delay(exc)
    )
    if delay is not None:
        metadata["server_retry_delay"] = delay
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
    if code is None:
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                code = error.get("code") or error.get("type")
            else:
                code = body.get("code") or body.get("type")
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


def _llm_provider_message(exc: Exception) -> str | None:
    message = getattr(exc, "message", None)
    if message is None:
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                message = error.get("message")
            else:
                message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    return _sanitize_provider_message(message)


def _sanitize_provider_message(message: str, *, max_length: int = 240) -> str:
    sanitized = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", message)
    sanitized = re.sub(r"(?i)(api[_ -]?key\s*[:=]\s*)\S+", r"\1[redacted]", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if len(sanitized) > max_length:
        return sanitized[: max_length - 3].rstrip() + "..."
    return sanitized


@dataclass(frozen=True)
class LLMErrorClassification:
    http_status: int
    error_code: str
    message: str


_RATE_LIMIT_MARKERS = ("429", "rate limit", "resource exhausted", "quota")
_UNAVAILABLE_MARKERS = ("temporarily unavailable", "service unavailable")
_LLM_RETRYABLE_MESSAGE_MARKERS = _RATE_LIMIT_MARKERS + _UNAVAILABLE_MARKERS


def classify_llm_error(exc: Exception) -> LLMErrorClassification:
    """Map a post-retry LLM exception to a user-facing classification."""
    if isinstance(exc, TimeoutError):
        return LLMErrorClassification(
            504,
            "timeout",
            "Yêu cầu mất quá nhiều thời gian, vui lòng thử lại.",
        )

    status_code = _llm_status_code(exc)
    code = _llm_error_code(exc)
    message_lower = str(exc).casefold()

    if code == "DEADLINE_EXCEEDED":
        return LLMErrorClassification(
            504,
            "timeout",
            "Yêu cầu mất quá nhiều thời gian, vui lòng thử lại.",
        )

    is_rate_limit = (
        status_code == 429
        or code in {"RESOURCE_EXHAUSTED"}
        or any(m in message_lower for m in _RATE_LIMIT_MARKERS)
    )
    if is_rate_limit:
        return LLMErrorClassification(
            503,
            "rate_limit",
            "Hệ thống đang quá tải, vui lòng thử lại sau ít phút.",
        )

    is_provider_down = (
        status_code in {500, 502, 503, 504}
        or code in {"UNAVAILABLE", "INTERNAL"}
        or any(m in message_lower for m in _UNAVAILABLE_MARKERS)
    )
    if is_provider_down:
        return LLMErrorClassification(
            503,
            "provider_unavailable",
            "Dịch vụ AI tạm thời gián đoạn, vui lòng thử lại.",
        )

    if isinstance(exc, (ConnectionError, OSError)):
        return LLMErrorClassification(
            503,
            "service_unavailable",
            "Không thể kết nối đến dịch vụ AI, vui lòng thử lại.",
        )

    return LLMErrorClassification(
        500,
        "internal_error",
        "Đã xảy ra lỗi không mong đợi, vui lòng thử lại.",
    )


class LLMReasoner:
    """LLM-backed reasoner using a provider-neutral interface."""

    def __init__(
        self,
        llm: Any,
        *,
        timeout_seconds: float,
        max_retries: int = 0,
        backoff_seconds: float = 0.5,
    ) -> None:
        self._llm = llm
        self._structured_llm = bind_structured_output(llm, ReasoningDecision)
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
        messages = self._finalize_messages(goal, memory)
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

    def _finalize_messages(self, goal: str, memory: Memory) -> list[Any]:
        history = "\n".join(step.model_dump_json() for step in memory.steps())
        return [
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

    async def stream_finalize(self, goal: str, memory: Memory) -> AsyncIterator[str]:
        astream = getattr(self._llm, "astream", None)
        if not callable(astream):
            final_response = await self.finalize(goal, memory)
            for start in range(0, len(final_response), 32):
                yield final_response[start : start + 32]
            return

        messages = self._finalize_messages(goal, memory)
        span_metadata = {
            "operation": "finalize-stream",
            "timeout_seconds": self._timeout_seconds,
        }
        with agent_span("agent-reasoner", metadata=span_metadata) as span:
            try:
                async for chunk in _astream_llm_with_retry(
                    lambda: astream(
                        messages,
                        config=langchain_config(
                            "reasoner-finalize-stream",
                            extra_metadata=span_metadata,
                        ),
                    ),
                    operation="reasoner-finalize-stream",
                    timeout_seconds=self._timeout_seconds,
                    max_retries=self._max_retries,
                    backoff_seconds=self._backoff_seconds,
                ):
                    text = _chunk_content(chunk)
                    if text:
                        yield text
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
                        f"Reasoner finalize stream failed with {type(exc).__name__}."
                    ),
                )
                raise

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
        self._structured_llm = bind_structured_output(llm, FallbackRouteDecision)
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
                    "Return tool='none' only when no tool can help. "
                    "Return valid JSON only. Do not wrap in markdown. "
                    "Match the FallbackRouteDecision schema exactly."
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
    """Fallback reasoner that asks an LLM router for a safe tool choice."""

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
                raise

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
        input=validated_input.model_dump(mode="json", exclude_none=True),
    )
    return None if _was_action_called(action, memory) else action


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
    for result in unique_results:
        title = result.get("title") or _source_label(result["url"])
        citation = f"[{title}]({result['url']})"
        bullets.append(f"- {citation}")

    return "\n\n".join(
        [
            "Tôi chưa thể xác minh kết luận trong câu hỏi vì bước tổng hợp "
            "nguồn đang không khả dụng. Các kết quả cùng chủ đề không đủ để "
            "khẳng định từng địa điểm, số liệu, điều kiện hoặc nơi bán mà bạn nêu.",
            "Các nguồn tìm được để kiểm tra thêm:\n" + "\n".join(bullets),
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
                provider="llm",
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
                provider="llm",
                error_type=type(exc).__name__,
            )
            return await self._fallback.finalize(goal, memory)

    async def stream_finalize(self, goal: str, memory: Memory) -> AsyncIterator[str]:
        primary_stream = getattr(self._primary, "stream_finalize", None)
        if callable(primary_stream):
            try:
                async for chunk in primary_stream(goal, memory):
                    yield chunk
                return
            except Exception as exc:
                logger.warning(
                    "agent_provider_fallback",
                    operation="stream_finalize",
                    provider="llm",
                    error_type=type(exc).__name__,
                )
        else:
            try:
                response = await self._primary.finalize(goal, memory)
                for start in range(0, len(response), 32):
                    yield response[start : start + 32]
                return
            except Exception as exc:
                logger.warning(
                    "agent_provider_fallback",
                    operation="stream_finalize",
                    provider="llm",
                    error_type=type(exc).__name__,
                )

        fallback_stream = getattr(self._fallback, "stream_finalize", None)
        if callable(fallback_stream):
            async for chunk in fallback_stream(goal, memory):
                yield chunk
            return
        response = await self._fallback.finalize(goal, memory)
        for start in range(0, len(response), 32):
            yield response[start : start + 32]


__all__ = [
    "FallbackRouteDecision",
    "FallbackReasoner",
    "LLMReasoner",
    "LLMRoutedFallbackReasoner",
    "LLMToolRouter",
    "REACT_PROMPT",
]
