"""Semantic source-priority policy for production agent tools."""

import json
from collections.abc import Sequence
from typing import Any, cast

import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from .prompts import TOOL_POLICY_PROMPT
from .react import Action, Memory, Tool, _was_action_called
from .reasoners import _ainvoke_llm_with_retry
from .tracing import agent_span, langchain_config, update_observation

logger = structlog.get_logger(__name__)


class ToolPolicyCall(BaseModel):
    tool: str
    input: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1)


class ToolPolicyDecision(BaseModel):
    actions: list[ToolPolicyCall] = Field(default_factory=list, max_length=4)
    rationale: str = Field(min_length=1)


class SemanticToolPolicy:
    """Use a structured LLM classifier to choose source-prioritized tools."""

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
            response_schema=ToolPolicyDecision.model_json_schema(),
        )
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    async def decide(
        self,
        goal: str,
        memory: Memory,
        tools: Sequence[Tool],
    ) -> Action | None:
        span_metadata = {
            "available_tools": [tool.name for tool in tools],
            "previous_tool_count": sum(
                1 for step in memory.steps() if step.action is not None
            ),
            "timeout_seconds": self._timeout_seconds,
        }
        with agent_span("agent-tool-policy", metadata=span_metadata) as span:
            try:
                decision = await self._classify(goal, memory, tools)
            except Exception as exc:
                logger.warning(
                    "agent_tool_policy_failed",
                    error_type=type(exc).__name__,
                )
                update_observation(
                    span,
                    operation="tool-policy",
                    metadata={**span_metadata, "error_type": type(exc).__name__},
                    level="ERROR",
                    status_message=(
                        f"Tool policy classification failed with {type(exc).__name__}."
                    ),
                )
                return None

            planned_actions = [
                _tool_call_metadata(tool_call) for tool_call in decision.actions
            ]
            skipped_actions: list[dict[str, Any]] = []
            for tool_call in decision.actions:
                action = _action_from_policy_call(tool_call, tools)
                if action is None:
                    skipped_actions.append(
                        {
                            **_tool_call_metadata(tool_call),
                            "skip_reason": "invalid_or_unavailable",
                        }
                    )
                    continue
                if _was_action_called(action, memory):
                    skipped_actions.append(
                        {
                            **_action_metadata(action),
                            "reason": tool_call.reason,
                            "skip_reason": "already_called",
                        }
                    )
                    continue

                selected_action = _action_metadata(action)
                metadata = {
                    **span_metadata,
                    "rationale": decision.rationale,
                    "planned_actions": planned_actions,
                    "selected_action": selected_action,
                    "skipped_actions": skipped_actions,
                }
                logger.info(
                    "agent_tool_policy_selected",
                    selected_tool=action.tool,
                    planned_tool_count=len(planned_actions),
                    skipped_tool_count=len(skipped_actions),
                )
                update_observation(
                    span,
                    operation="tool-policy",
                    metadata=metadata,
                    output={
                        "selected_action": selected_action,
                        "rationale": decision.rationale,
                    },
                )
                return action

            metadata = {
                **span_metadata,
                "rationale": decision.rationale,
                "planned_actions": planned_actions,
                "selected_action": None,
                "skipped_actions": skipped_actions,
            }
            logger.info(
                "agent_tool_policy_no_action",
                planned_tool_count=len(planned_actions),
                skipped_tool_count=len(skipped_actions),
            )
            update_observation(
                span,
                operation="tool-policy",
                metadata=metadata,
                output={
                    "selected_action": None,
                    "rationale": decision.rationale,
                },
            )
            return None

    async def _classify(
        self,
        goal: str,
        memory: Memory,
        tools: Sequence[Tool],
    ) -> ToolPolicyDecision:
        tool_catalog = "\n".join(
            f"- {tool.name}: {tool.description}\n  input_schema={tool.schema()}"
            for tool in tools
        )
        previous_calls = (
            "\n".join(
                _format_previous_call(step.action.tool, step.action.input)
                for step in memory.steps()
                if step.action is not None
            )
            or "(no previous tool calls)"
        )
        messages = [
            SystemMessage(content=TOOL_POLICY_PROMPT),
            HumanMessage(
                content=(
                    f"User goal:\n{goal}\n\n"
                    f"Available tools:\n{tool_catalog}\n\n"
                    f"Previous tool calls:\n{previous_calls}"
                )
            ),
        ]
        response = await _ainvoke_llm_with_retry(
            lambda: self._structured_llm.ainvoke(
                messages,
                config=langchain_config(
                    "tool-policy-classifier",
                    extra_metadata={"timeout_seconds": self._timeout_seconds},
                ),
            ),
            operation="tool-policy-classifier",
            timeout_seconds=self._timeout_seconds,
            max_retries=self._max_retries,
            backoff_seconds=self._backoff_seconds,
        )
        return _parse_tool_policy_decision(response)


def _parse_tool_policy_decision(response: Any) -> ToolPolicyDecision:
    if isinstance(response, ToolPolicyDecision):
        return response
    if isinstance(response, dict):
        parsed = response.get("parsed")
        if parsed is not None:
            return _parse_tool_policy_decision(parsed)
        if response.get("parsing_error") is not None and "raw" in response:
            return _parse_tool_policy_decision(response["raw"])
        return ToolPolicyDecision.model_validate(response)
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return ToolPolicyDecision.model_validate_json(content)
    return ToolPolicyDecision.model_validate(content)


def _format_previous_call(tool: str, input_data: dict[str, Any]) -> str:
    serialized_input = json.dumps(input_data, ensure_ascii=False, sort_keys=True)
    return f"- {tool}: {serialized_input}"


def _tool_call_metadata(tool_call: ToolPolicyCall) -> dict[str, Any]:
    return {
        "tool": tool_call.tool,
        "input": tool_call.input,
        "reason": tool_call.reason,
    }


def _action_metadata(action: Action) -> dict[str, Any]:
    return {
        "tool": action.tool,
        "input": action.input,
    }


def _action_from_policy_call(
    tool_call: ToolPolicyCall,
    tools: Sequence[Tool],
) -> Action | None:
    tool = next(
        (candidate for candidate in tools if candidate.name == tool_call.tool),
        None,
    )
    if tool is None:
        return None
    try:
        validated_input = tool.input_model.model_validate(tool_call.input)
    except Exception:
        return None
    return Action(tool=tool.name, input=validated_input.model_dump(mode="json"))


__all__ = [
    "SemanticToolPolicy",
    "ToolPolicyCall",
    "ToolPolicyDecision",
    "TOOL_POLICY_PROMPT",
]
