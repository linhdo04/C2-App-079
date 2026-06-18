"""Shared test doubles for agent components."""

from typing import Any


class FakePolicyLLM:
    def __init__(self, decision: dict[str, Any]) -> None:
        self.decision = decision
        self.calls = 0
        self.messages: Any = None

    def bind(self, **kwargs: Any) -> "FakePolicyLLM":
        return self

    async def ainvoke(self, messages: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        self.messages = messages
        return self.decision
