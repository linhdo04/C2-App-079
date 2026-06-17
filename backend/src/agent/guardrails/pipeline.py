"""Layered deterministic guardrails for agent input, tools, and output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

GuardrailStage = Literal["input", "tool_input", "tool_output", "output"]

SAFE_BLOCKED_RESPONSE = (
    "Tôi không thể xử lý yêu cầu này vì nội dung có dấu hiệu không an toàn. "
    "Vui lòng diễn đạt lại yêu cầu theo hướng hỗ trợ sản xuất nông nghiệp."
)


@dataclass(frozen=True)
class GuardrailDecision:
    content: str
    blocked: bool = False
    reason: str | None = None


class GuardrailPipeline:
    """Fast deterministic guardrails inspired by LangChain middleware layers."""

    _EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
    _CREDIT_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
    _SECRET_PATTERNS = (
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
        re.compile(r"\btvly-[A-Za-z0-9_-]{16,}\b"),
        re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
        re.compile(
            r"\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[^'\"\s]{8,}",
            re.I,
        ),
    )
    _PROMPT_INJECTION_PATTERNS = (
        re.compile(r"\bignore (?:all )?(?:previous|above|system) instructions\b", re.I),
        re.compile(
            r"\bdisregard (?:all )?(?:previous|above|system) instructions\b", re.I
        ),
        re.compile(r"\breveal (?:the )?(?:system|developer) prompt\b", re.I),
        re.compile(r"\bprint (?:the )?(?:system|developer) prompt\b", re.I),
        re.compile(r"\bjailbreak\b", re.I),
        re.compile(
            r"bỏ qua (?:tất cả )?(?:hướng dẫn|chỉ dẫn) (?:trước|hệ thống)", re.I
        ),
        re.compile(r"tiết lộ (?:system prompt|developer prompt|prompt hệ thống)", re.I),
    )

    def __init__(
        self,
        *,
        enabled: bool = True,
        redact_pii: bool = True,
        block_secrets: bool = True,
        block_prompt_injection: bool = True,
    ) -> None:
        self.enabled = enabled
        self.redact_pii = redact_pii
        self.block_secrets = block_secrets
        self.block_prompt_injection = block_prompt_injection

    def check_input(self, content: str) -> GuardrailDecision:
        return self._check_text(content, stage="input")

    def check_tool_input(self, tool: str, payload: dict[str, Any]) -> GuardrailDecision:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return self._check_text(serialized, stage="tool_input", tool=tool)

    def check_tool_output(self, tool: str, content: str) -> GuardrailDecision:
        return self._check_text(content, stage="tool_output", tool=tool)

    def check_output(self, content: str) -> GuardrailDecision:
        return self._check_text(content, stage="output")

    def _check_text(
        self,
        content: str,
        *,
        stage: GuardrailStage,
        tool: str | None = None,
    ) -> GuardrailDecision:
        if not self.enabled:
            return GuardrailDecision(content=content)

        if self.block_secrets and self._contains_secret(content):
            return GuardrailDecision(
                content=SAFE_BLOCKED_RESPONSE,
                blocked=True,
                reason=f"{stage}:secret",
            )

        if (
            self.block_prompt_injection
            and stage in {"input", "tool_output"}
            and self._contains_prompt_injection(content)
        ):
            return GuardrailDecision(
                content=SAFE_BLOCKED_RESPONSE,
                blocked=True,
                reason=f"{stage}:prompt_injection",
            )

        if not self.redact_pii:
            return GuardrailDecision(content=content)

        sanitized = self._redact_email(content)
        sanitized = self._mask_credit_cards(sanitized)
        return GuardrailDecision(content=sanitized)

    def _contains_secret(self, content: str) -> bool:
        return any(pattern.search(content) for pattern in self._SECRET_PATTERNS)

    def _contains_prompt_injection(self, content: str) -> bool:
        return any(
            pattern.search(content) for pattern in self._PROMPT_INJECTION_PATTERNS
        )

    def _redact_email(self, content: str) -> str:
        return self._EMAIL_RE.sub("[REDACTED_EMAIL]", content)

    def _mask_credit_cards(self, content: str) -> str:
        def replace(match: re.Match[str]) -> str:
            candidate = match.group(0)
            digits = re.sub(r"\D", "", candidate)
            if not self._valid_luhn(digits):
                return candidate
            return f"[MASKED_CREDIT_CARD_****{digits[-4:]}]"

        return self._CREDIT_CARD_RE.sub(replace, content)

    @staticmethod
    def _valid_luhn(digits: str) -> bool:
        if not 13 <= len(digits) <= 19:
            return False
        checksum = 0
        parity = len(digits) % 2
        for index, character in enumerate(digits):
            value = int(character)
            if index % 2 == parity:
                value *= 2
                if value > 9:
                    value -= 9
            checksum += value
        return checksum % 10 == 0


def build_default_guardrails(settings: Any) -> GuardrailPipeline:
    return GuardrailPipeline(
        enabled=settings.agent_guardrails_enabled,
        redact_pii=settings.agent_guardrails_redact_pii,
        block_secrets=settings.agent_guardrails_block_secrets,
        block_prompt_injection=settings.agent_guardrails_block_prompt_injection,
    )
