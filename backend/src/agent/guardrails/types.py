"""Shared guardrail data types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

GuardrailStage = Literal["input", "tool_input", "tool_output", "output"]


@dataclass(frozen=True)
class GuardrailContext:
    stage: GuardrailStage
    tool: str | None = None


@dataclass(frozen=True)
class GuardrailDecision:
    content: str
    blocked: bool = False
    reason: str | None = None
