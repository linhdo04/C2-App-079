"""Deterministic fast routing before the full agent runtime."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

PreRouteKind = Literal["final", "clarify"]


@dataclass(frozen=True)
class PreRouteDecision:
    kind: PreRouteKind
    response: str


_GREETING_RESPONSE = (
    "Xin chào! Tôi có thể hỗ trợ bạn về canh tác, dữ liệu đồng ruộng, "
    "tưới tiêu, sâu bệnh hoặc vận hành drone."
)
_THANKS_RESPONSE = "Rất vui được hỗ trợ bạn."
_ACK_RESPONSE = "Tôi đã hiểu. Bạn cần tôi hỗ trợ thêm phần nào?"

_GREETING_PATTERNS = (
    re.compile(r"^(?:xin\s+)?ch[aà]o(?:\s+(?:b[aạ]n|ad|admin|anh|chị|em))?[!.?]*$"),
    re.compile(r"^(?:hi|hello|hey)[!.?]*$", re.IGNORECASE),
)
_THANKS_PATTERNS = (
    re.compile(r"^(?:c[aả]m\s+ơn|thanks|thank\s+you|tks|thx)(?:\s+.*)?[!.?]*$"),
)
_ACK_PATTERNS = (
    re.compile(r"^(?:ok|okay|ừ|uh|ờ|vâng|dạ|được|hiểu rồi)[!.?]*$", re.IGNORECASE),
)


def pre_route(question: str) -> PreRouteDecision | None:
    """Return a deterministic response for low-risk fast-path cases.

    Keep this intentionally small. Broader natural-language routing belongs to
    the lightweight LLM intent router, not an expanding rule list.
    """

    normalized = _normalize_text(question)
    if not normalized:
        return PreRouteDecision(
            kind="clarify",
            response=(
                "Bạn muốn tôi hỗ trợ vấn đề gì về canh tác hoặc dữ liệu đồng ruộng?"
            ),
        )

    if _matches_any(normalized, _GREETING_PATTERNS):
        return PreRouteDecision(kind="final", response=_GREETING_RESPONSE)
    if _matches_any(normalized, _THANKS_PATTERNS):
        return PreRouteDecision(kind="final", response=_THANKS_RESPONSE)
    if _matches_any(normalized, _ACK_PATTERNS):
        return PreRouteDecision(kind="final", response=_ACK_RESPONSE)

    return None


def _matches_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    normalized = re.sub(r"\s+", " ", normalized).strip().casefold()
    return normalized


__all__ = ["PreRouteDecision", "pre_route"]
