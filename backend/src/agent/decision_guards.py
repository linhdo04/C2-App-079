"""Data-driven decision guard policy for the agent loop."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class _ActionLike(Protocol):
    tool: str
    input: dict[str, Any]


class _MemoryLike(Protocol):
    def steps(self) -> tuple[Any, ...]: ...


@dataclass(frozen=True)
class DecisionGuardCondition:
    type: str
    tool: str | None = None


@dataclass(frozen=True)
class DecisionGuardRule:
    name: str
    conditions: tuple[DecisionGuardCondition, ...]
    response: str


@dataclass(frozen=True)
class ToolPolicySkipRule:
    tool: str
    action_input_key: str


@dataclass(frozen=True)
class DecisionGuardPolicy:
    external_search_intent_patterns: tuple[re.Pattern[str], ...]
    ambiguous_day_only_patterns: tuple[re.Pattern[str], ...]
    complete_date_patterns: tuple[re.Pattern[str], ...]
    telemetry_no_data_markers: tuple[str, ...]
    point_telemetry_query_kinds: frozenset[str]
    tool_policy_skip_after_terminal_observation: ToolPolicySkipRule
    rules: tuple[DecisionGuardRule, ...]

    def evaluate(
        self, *, goal: str, action: _ActionLike, memory: _MemoryLike
    ) -> str | None:
        for rule in self.rules:
            if all(
                self._matches_condition(
                    condition, goal=goal, action=action, memory=memory
                )
                for condition in rule.conditions
            ):
                return rule.response
        return None

    def should_skip_tool_policy_after_terminal_observation(
        self,
        *,
        goal: str,
        memory: _MemoryLike,
    ) -> bool:
        if self.has_explicit_external_search_intent(goal):
            return False
        steps = memory.steps()
        if not steps:
            return False
        last_action = steps[-1].action
        skip_rule = self.tool_policy_skip_after_terminal_observation
        return (
            last_action is not None
            and last_action.tool == skip_rule.tool
            and skip_rule.action_input_key in last_action.input
        )

    def has_explicit_external_search_intent(self, goal: str) -> bool:
        return any(
            pattern.search(goal) for pattern in self.external_search_intent_patterns
        )

    def _matches_condition(
        self,
        condition: DecisionGuardCondition,
        *,
        goal: str,
        action: _ActionLike,
        memory: _MemoryLike,
    ) -> bool:
        match condition.type:
            case "action_tool_is":
                return condition.tool is not None and action.tool == condition.tool
            case "memory_has_empty_telemetry_observation":
                return self._has_empty_telemetry_observation(memory)
            case "goal_lacks_external_search_intent":
                return not self.has_explicit_external_search_intent(goal)
            case "goal_has_ambiguous_day_only_date":
                return self._has_ambiguous_day_only_date(goal)
            case "action_lacks_point_telemetry_query":
                return not self._has_point_telemetry_query(action)
            case _:
                raise ValueError(
                    f"Unsupported decision guard condition: {condition.type}"
                )

    def _has_empty_telemetry_observation(self, memory: _MemoryLike) -> bool:
        telemetry_tool = self.tool_policy_skip_after_terminal_observation.tool
        return any(
            step.action is not None
            and step.action.tool == telemetry_tool
            and any(
                marker in step.observation for marker in self.telemetry_no_data_markers
            )
            for step in memory.steps()
        )

    def _has_ambiguous_day_only_date(self, goal: str) -> bool:
        return any(
            pattern.search(goal) for pattern in self.ambiguous_day_only_patterns
        ) and not any(pattern.search(goal) for pattern in self.complete_date_patterns)

    def _has_point_telemetry_query(self, action: _ActionLike) -> bool:
        query_kinds = action.input.get(
            self.tool_policy_skip_after_terminal_observation.action_input_key
        )
        return isinstance(query_kinds, list) and any(
            query_kind in self.point_telemetry_query_kinds for query_kind in query_kinds
        )


def load_decision_guard_policy(path: Path | None = None) -> DecisionGuardPolicy:
    source = path or Path(__file__).with_name("decision_guard_rules.json")
    raw = json.loads(source.read_text(encoding="utf-8"))
    return DecisionGuardPolicy(
        external_search_intent_patterns=_compile_patterns(
            raw["external_search_intent_patterns"]
        ),
        ambiguous_day_only_patterns=_compile_patterns(
            raw["ambiguous_day_only_patterns"]
        ),
        complete_date_patterns=_compile_patterns(raw["complete_date_patterns"]),
        telemetry_no_data_markers=tuple(raw["telemetry_no_data_markers"]),
        point_telemetry_query_kinds=frozenset(raw["point_telemetry_query_kinds"]),
        tool_policy_skip_after_terminal_observation=ToolPolicySkipRule(
            tool=raw["tool_policy_skip_after_terminal_observation"]["tool"],
            action_input_key=raw["tool_policy_skip_after_terminal_observation"][
                "action_input_key"
            ],
        ),
        rules=tuple(_parse_rules(raw["rules"])),
    )


def _compile_patterns(patterns: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


def _parse_rules(raw_rules: Sequence[dict[str, Any]]) -> list[DecisionGuardRule]:
    rules: list[DecisionGuardRule] = []
    for raw_rule in raw_rules:
        rules.append(
            DecisionGuardRule(
                name=raw_rule["name"],
                conditions=tuple(
                    DecisionGuardCondition(
                        type=condition["type"],
                        tool=condition.get("tool"),
                    )
                    for condition in raw_rule["conditions"]
                ),
                response=raw_rule["response"],
            )
        )
    return rules


__all__ = [
    "DecisionGuardPolicy",
    "load_decision_guard_policy",
]
