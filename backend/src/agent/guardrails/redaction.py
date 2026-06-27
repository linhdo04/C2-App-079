"""Deterministic PII redaction guardrails."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .types import GuardrailContext, GuardrailDecision


@dataclass(frozen=True)
class EmailRedactionGuardrail:
    """Redact email addresses using LangChain PII middleware semantics."""

    pattern: re.Pattern[str]

    def apply(self, content: str, context: GuardrailContext) -> GuardrailDecision:
        return GuardrailDecision(content=self.pattern.sub("[REDACTED_EMAIL]", content))


@dataclass(frozen=True)
class CreditCardMaskingGuardrail:
    """Mask Luhn-valid credit card numbers while preserving the last four digits."""

    pattern: re.Pattern[str]

    def apply(self, content: str, context: GuardrailContext) -> GuardrailDecision:
        return GuardrailDecision(content=self.pattern.sub(self._replace, content))

    def _replace(self, match: re.Match[str]) -> str:
        candidate = match.group(0)
        digits = re.sub(r"\D", "", candidate)
        if not self._valid_luhn(digits):
            return candidate
        return f"[MASKED_CREDIT_CARD_****{digits[-4:]}]"

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
