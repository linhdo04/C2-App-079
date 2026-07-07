"""Layered guardrail pipeline for agent input, tool calls, and output."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import structlog
from pydantic import BaseModel, Field

from ..tracing import agent_span, current_trace_context, update_observation
from .input_rails import PatternBlockGuardrail
from .redaction import CreditCardMaskingGuardrail, EmailRedactionGuardrail
from .risk import GuardrailRiskPattern, GuardrailRiskScore, GuardrailRiskScorer
from .types import GuardrailContext, GuardrailDecision, GuardrailStage

logger = structlog.get_logger(__name__)


class GuardrailPIIRules(BaseModel):
    email_pattern: str = Field(min_length=1)
    credit_card_pattern: str = Field(min_length=1)


class GuardrailRiskPatternRules(BaseModel):
    name: str = Field(min_length=1)
    weight: int = Field(ge=0, le=100)
    pattern: str = Field(min_length=1)


class GuardrailRiskRules(BaseModel):
    llm_guardrail_threshold: int = Field(ge=0, le=100)
    medium_threshold: int = Field(ge=0, le=100)
    stage_weights: dict[GuardrailStage, int] = Field(default_factory=dict)
    tool_weights: dict[str, int] = Field(default_factory=dict)
    patterns: list[GuardrailRiskPatternRules] = Field(default_factory=list)


class GuardrailRules(BaseModel):
    blocked_response: str = Field(min_length=1)
    pii: GuardrailPIIRules
    secrets: list[str] = Field(min_length=1)
    prompt_injection: list[str] = Field(min_length=1)
    risk: GuardrailRiskRules


class Guardrail(Protocol):
    """Middleware-like guardrail applied at one or more agent stages."""

    def apply(self, content: str, context: GuardrailContext) -> GuardrailDecision: ...


class GuardrailPipeline:
    """Composable guardrails inspired by LangChain agent middleware hooks.

    LangChain's docs recommend layered deterministic and model-based middleware
    at before-agent, around-tool, and after-agent points. This project uses a
    custom LangGraph loop, so the public API stays stable while this pipeline
    mirrors those middleware checkpoints through explicit stage methods.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        redact_pii: bool = True,
        block_secrets: bool = True,
        block_prompt_injection: bool = True,
        rules_path: Path | None = None,
        rails: Sequence[Guardrail] | None = None,
        risk_scorer: GuardrailRiskScorer | None = None,
    ) -> None:
        self.enabled = enabled
        self.rules_path = rules_path or Path(__file__).with_name("guardrail_rules.json")
        raw = self._load_rules()
        self.risk_scorer = risk_scorer or self._build_risk_scorer(raw.risk)
        self.rails = (
            tuple(rails)
            if rails is not None
            else tuple(
                self._build_default_rails(
                    raw,
                    redact_pii=redact_pii,
                    block_secrets=block_secrets,
                    block_prompt_injection=block_prompt_injection,
                )
            )
        )

    def check_input(self, content: str) -> GuardrailDecision:
        return self._apply(content, GuardrailContext(stage="input"))

    def check_tool_input(self, tool: str, payload: dict[str, Any]) -> GuardrailDecision:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return self._apply(serialized, GuardrailContext(stage="tool_input", tool=tool))

    def check_tool_output(self, tool: str, content: str) -> GuardrailDecision:
        return self._apply(content, GuardrailContext(stage="tool_output", tool=tool))

    def check_output(self, content: str) -> GuardrailDecision:
        return self._apply(content, GuardrailContext(stage="output"))

    def _apply(self, content: str, context: GuardrailContext) -> GuardrailDecision:
        if not self.enabled:
            return GuardrailDecision(content=content)

        with agent_span(
            "agent-guardrail",
            metadata={
                "stage": context.stage,
                "tool": context.tool,
                "input_characters": len(content),
            },
        ) as span:
            risk = self.risk_scorer.score(content, context)
            self._log_risk(risk, context)

            current = content
            for rail in self.rails:
                decision = rail.apply(current, context)
                if decision.blocked:
                    update_observation(
                        span,
                        metadata={
                            "blocked": True,
                            "reason": decision.reason,
                            "risk_score": risk.score,
                        },
                    )
                    return decision
                current = decision.content
            update_observation(
                span,
                metadata={
                    "blocked": False,
                    "redacted": current != content,
                    "output_characters": len(current),
                    "risk_score": risk.score,
                },
            )
            return GuardrailDecision(content=current)

    def _load_rules(self) -> GuardrailRules:
        return GuardrailRules.model_validate_json(
            self.rules_path.read_text(encoding="utf-8")
        )

    def _build_default_rails(
        self,
        raw: GuardrailRules,
        *,
        redact_pii: bool,
        block_secrets: bool,
        block_prompt_injection: bool,
    ) -> list[Guardrail]:
        rails: list[Guardrail] = []
        blocked_response = raw.blocked_response
        if block_secrets:
            rails.append(
                PatternBlockGuardrail(
                    name="secret",
                    patterns=_compile_patterns(raw.secrets),
                    stages=frozenset(("input", "tool_input", "tool_output", "output")),
                    blocked_response=blocked_response,
                )
            )
        if block_prompt_injection:
            rails.append(
                PatternBlockGuardrail(
                    name="prompt_injection",
                    patterns=_compile_patterns(raw.prompt_injection),
                    stages=frozenset(("input", "tool_output")),
                    blocked_response=blocked_response,
                )
            )
        if redact_pii:
            pii = raw.pii
            rails.extend(
                (
                    EmailRedactionGuardrail(
                        re.compile(pii.email_pattern, re.IGNORECASE)
                    ),
                    CreditCardMaskingGuardrail(re.compile(pii.credit_card_pattern)),
                )
            )
        return rails

    def _build_risk_scorer(self, raw: GuardrailRiskRules) -> GuardrailRiskScorer:
        return GuardrailRiskScorer(
            llm_guardrail_threshold=raw.llm_guardrail_threshold,
            medium_threshold=raw.medium_threshold,
            stage_weights=raw.stage_weights,
            tool_weights=raw.tool_weights,
            patterns=tuple(
                GuardrailRiskPattern(
                    name=pattern.name,
                    pattern=re.compile(pattern.pattern, re.IGNORECASE),
                    weight=pattern.weight,
                )
                for pattern in raw.patterns
            ),
        )

    def _log_risk(
        self,
        risk: GuardrailRiskScore,
        context: GuardrailContext,
    ) -> None:
        if risk.score <= 0:
            return
        trace_context = current_trace_context()
        logger.info(
            "agent_guardrail_risk_scored",
            run_id=trace_context.run_id if trace_context is not None else None,
            stage=context.stage,
            tool=context.tool,
            score=risk.score,
            level=risk.level,
            reasons=list(risk.reasons),
            llm_guardrail_recommended=risk.llm_guardrail_recommended,
        )


def _compile_patterns(patterns: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


def build_default_guardrails(settings: Any) -> GuardrailPipeline:
    return GuardrailPipeline(
        enabled=settings.agent_guardrails_enabled,
        redact_pii=settings.agent_guardrails_redact_pii,
        block_secrets=settings.agent_guardrails_block_secrets,
        block_prompt_injection=settings.agent_guardrails_block_prompt_injection,
    )
