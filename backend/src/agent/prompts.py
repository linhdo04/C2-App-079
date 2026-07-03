"""Agent prompts loaded from LangSmith with safe local fallbacks."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.config import settings

from . import tracing
from .prompt_defaults import (
    DEFAULT_INTENT_ROUTER_PROMPT,
    DEFAULT_REACT_PROMPT,
    DEFAULT_SEARCH_FILTER_PROMPT,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TOOL_POLICY_PROMPT,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptSpec:
    name: str
    fallback: str
    required_markers: tuple[str, ...]


def _prompt_name(name: str) -> str:
    """Build the LangSmith prompt name for the current environment.

    Example:
        LANGSMITH_PROMPT_PREFIX=local_
        system_prompt -> local_system_prompt
    """
    prefix = getattr(settings, "app_env", "") or ""
    return f"{prefix}_{name}"


def _load_prompt(spec: PromptSpec) -> str:
    if not tracing.langsmith_configured():
        return spec.fallback

    prompt_name = _prompt_name(spec.name)

    try:
        prompt = tracing._get_langsmith_client().pull_prompt(prompt_name)
    except Exception as exc:  # pragma: no cover - depends on external LangSmith
        logger.warning("Falling back to local %s prompt: %s", prompt_name, exc)
        return spec.fallback

    text = _prompt_text(prompt).strip()

    if not text:
        logger.warning(
            "Falling back to local %s prompt because LangSmith content is empty",
            prompt_name,
        )
        return spec.fallback

    missing_markers = [marker for marker in spec.required_markers if marker not in text]

    if missing_markers:
        logger.warning(
            "Falling back to local %s prompt because required markers are missing: %s",
            prompt_name,
            ", ".join(missing_markers),
        )
        return spec.fallback

    return text


def _prompt_text(prompt: object) -> str:
    if isinstance(prompt, str):
        return prompt

    template = getattr(prompt, "template", None)
    if isinstance(template, str):
        return template

    messages = getattr(prompt, "messages", None)
    if isinstance(messages, list):
        parts: list[str] = []

        for message in messages:
            message_template = getattr(message, "template", None)
            if isinstance(message_template, str):
                parts.append(message_template)
                continue

            nested_prompt = getattr(message, "prompt", None)
            nested_template = getattr(nested_prompt, "template", None)
            if isinstance(nested_template, str):
                parts.append(nested_template)

        if parts:
            return "\n\n".join(parts)

    return str(prompt)


SYSTEM_PROMPT = _load_prompt(
    PromptSpec(
        name="system_prompt",
        fallback=DEFAULT_SYSTEM_PROMPT,
        required_markers=(
            "agricultural production in Vietnam",
            "source-named inline citation links",
            "exact telemetry minimum or maximum occurs multiple times",
            "Decompose the user's statement into its material claims",
        ),
    )
)

REACT_PROMPT = _load_prompt(
    PromptSpec(
        name="react_prompt",
        fallback=DEFAULT_REACT_PROMPT,
        required_markers=("ReAct agent loop", "one short sentence"),
    )
)

TOOL_POLICY_PROMPT = _load_prompt(
    PromptSpec(
        name="tool_policy_prompt",
        fallback=DEFAULT_TOOL_POLICY_PROMPT,
        required_markers=("semantic tool policy classifier", "ToolPolicyDecision"),
    )
)

SEARCH_FILTER_PROMPT = _load_prompt(
    PromptSpec(
        name="search_filter_prompt",
        fallback=DEFAULT_SEARCH_FILTER_PROMPT,
        required_markers=(
            "filter web search results before they enter ReAct memory",
            "SearchFilterDecision schema",
            "Relevance to the same topic does not verify a claim",
        ),
    )
)

INTENT_ROUTER_PROMPT = _load_prompt(
    PromptSpec(
        name="intent_router_prompt",
        fallback=DEFAULT_INTENT_ROUTER_PROMPT,
        required_markers=("fast intent router", "IntentRouteDecision"),
    )
)
