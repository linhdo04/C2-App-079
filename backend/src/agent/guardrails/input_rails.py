"""Deterministic block guardrails for unsafe input and tool content."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from .types import GuardrailContext, GuardrailDecision, GuardrailStage


@dataclass(frozen=True)
class PatternBlockGuardrail:
    """Block content when any configured pattern matches the current stage."""

    name: str
    patterns: Sequence[re.Pattern[str]]
    stages: frozenset[GuardrailStage]
    blocked_response: str
    tools: frozenset[str] | None = None

    def apply(self, content: str, context: GuardrailContext) -> GuardrailDecision:
        if context.stage not in self.stages:
            return GuardrailDecision(content=content)
        if self.tools is not None and context.tool not in self.tools:
            return GuardrailDecision(content=content)
        if not any(pattern.search(content) for pattern in self.patterns):
            return GuardrailDecision(content=content)
        return GuardrailDecision(
            content=self.blocked_response,
            blocked=True,
            reason=f"{context.stage}:{self.name}",
        )
