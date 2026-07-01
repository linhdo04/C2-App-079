"""Lightweight LLM intent router for simple chat turns."""

import json
from collections.abc import Sequence
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator, model_validator

from .prompts import INTENT_ROUTER_PROMPT
from .react import ConversationMessage, InMemoryMemory
from .reasoners import _ainvoke_llm_with_retry
from .structured import bind_structured_output
from .tracing import langchain_config

IntentRoute = Literal["direct_answer", "clarify", "full_agent"]


class IntentRouteDecision(BaseModel):
    route: IntentRoute
    answer: str | None = None
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)

    @field_validator("answer", mode="before")
    @classmethod
    def normalize_blank_answer(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def require_answer_for_terminal_routes(self) -> "IntentRouteDecision":
        if self.route in {"direct_answer", "clarify"} and not self.answer:
            raise ValueError("answer is required for direct_answer and clarify")
        if self.route == "full_agent":
            self.answer = None
        return self


class IntentRouter:
    """Classify whether a turn can skip the full ReAct agent."""

    def __init__(
        self,
        llm: Any,
        *,
        timeout_seconds: float,
        min_confidence: float,
        max_retries: int = 0,
        backoff_seconds: float = 0.5,
    ) -> None:
        self._structured_llm = bind_structured_output(llm, IntentRouteDecision)
        self._timeout_seconds = timeout_seconds
        self._min_confidence = min_confidence
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    async def route(
        self,
        question: str,
        memory: InMemoryMemory,
    ) -> IntentRouteDecision | None:
        response = await _ainvoke_llm_with_retry(
            lambda: self._structured_llm.ainvoke(
                _messages(question, memory.conversation()),
                config=langchain_config(
                    "intent-router",
                    extra_metadata={"timeout_seconds": self._timeout_seconds},
                ),
            ),
            operation="intent-router",
            timeout_seconds=self._timeout_seconds,
            max_retries=self._max_retries,
            backoff_seconds=self._backoff_seconds,
        )
        decision = _parse_intent_route_decision(response)
        if decision.confidence < self._min_confidence:
            return None
        return decision


def _messages(question: str, history: Sequence[ConversationMessage]) -> list[Any]:
    recent_history = "\n".join(
        f"{message.role}: {_shorten(message.content, 600)}" for message in history[-4:]
    )
    schema = json.dumps(IntentRouteDecision.model_json_schema(), ensure_ascii=False)
    return [
        SystemMessage(
            content=f"{INTENT_ROUTER_PROMPT}\n\nIntentRouteDecision schema:\n{schema}"
        ),
        HumanMessage(
            content=(
                f"Recent conversation:\n{recent_history or '(none)'}\n\n"
                f"User message:\n{question}"
            )
        ),
    ]


def _parse_intent_route_decision(response: Any) -> IntentRouteDecision:
    if isinstance(response, IntentRouteDecision):
        return response
    if isinstance(response, dict):
        parsed = response.get("parsed")
        if parsed is not None:
            return _parse_intent_route_decision(parsed)
        if response.get("parsing_error") is not None and "raw" in response:
            return _parse_intent_route_decision(response["raw"])
        return IntentRouteDecision.model_validate(response)
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return IntentRouteDecision.model_validate_json(content)
    return IntentRouteDecision.model_validate(content)


def _shorten(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


__all__ = ["IntentRouteDecision", "IntentRouter"]
