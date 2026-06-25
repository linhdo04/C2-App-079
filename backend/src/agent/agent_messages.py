"""Config-backed user-facing agent messages."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentMessages:
    stream_status: dict[str, str]
    tool_status: dict[str, str]
    fallback_responses: dict[str, str]

    def status(self, key: str) -> str:
        return self.stream_status[key]

    def tool(self, tool: str) -> str:
        template = self.tool_status.get(tool, self.tool_status["default"])
        return template.format(tool=tool)

    def fallback(self, key: str) -> str:
        return self.fallback_responses[key]


def load_agent_messages(path: Path | None = None) -> AgentMessages:
    source = path or Path(__file__).with_name("agent_messages.json")
    raw: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    return AgentMessages(
        stream_status=dict(raw["stream_status"]),
        tool_status={
            "default": raw["tool_status"]["default"],
            **dict(raw["tool_status"]["tools"]),
        },
        fallback_responses=dict(raw["fallback_responses"]),
    )


__all__ = ["AgentMessages", "load_agent_messages"]
