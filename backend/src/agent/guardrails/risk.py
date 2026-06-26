"""Deterministic risk scoring for optional model-based guardrails."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from .types import GuardrailContext, GuardrailStage

GuardrailRiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class GuardrailRiskPattern:
    name: str
    pattern: re.Pattern[str]
    weight: int


@dataclass(frozen=True)
class GuardrailRiskScore:
    score: int
    level: GuardrailRiskLevel
    reasons: tuple[str, ...]
    llm_guardrail_recommended: bool


class GuardrailRiskScorer:
    """Score whether content is risky enough for future LLM guardrails."""

    def __init__(
        self,
        *,
        llm_guardrail_threshold: int,
        medium_threshold: int,
        stage_weights: Mapping[GuardrailStage, int],
        tool_weights: Mapping[str, int],
        patterns: Sequence[GuardrailRiskPattern],
    ) -> None:
        if not 0 <= medium_threshold <= llm_guardrail_threshold <= 100:
            raise ValueError("Invalid guardrail risk thresholds")
        self.llm_guardrail_threshold = llm_guardrail_threshold
        self.medium_threshold = medium_threshold
        self.stage_weights = dict(stage_weights)
        self.tool_weights = dict(tool_weights)
        self.patterns = tuple(patterns)

    def score(self, content: str, context: GuardrailContext) -> GuardrailRiskScore:
        score = 0
        reasons: list[str] = []

        stage_weight = self.stage_weights.get(context.stage, 0)
        if stage_weight > 0:
            score += stage_weight
            reasons.append(f"stage:{context.stage}")

        if context.tool is not None:
            tool_weight = self.tool_weights.get(context.tool, 0)
            if tool_weight > 0:
                score += tool_weight
                reasons.append(f"tool:{context.tool}")

        for rule in self.patterns:
            if rule.pattern.search(content):
                score += rule.weight
                reasons.append(f"pattern:{rule.name}")

        capped_score = min(score, 100)
        return GuardrailRiskScore(
            score=capped_score,
            level=self._level(capped_score),
            reasons=tuple(reasons),
            llm_guardrail_recommended=(capped_score >= self.llm_guardrail_threshold),
        )

    def _level(self, score: int) -> GuardrailRiskLevel:
        if score >= self.llm_guardrail_threshold:
            return "high"
        if score >= self.medium_threshold:
            return "medium"
        return "low"


__all__ = [
    "GuardrailRiskPattern",
    "GuardrailRiskScore",
    "GuardrailRiskScorer",
]
