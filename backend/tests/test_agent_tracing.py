from typing import Any

from agent.tracing import (
    AgentTraceContext,
    langchain_config,
    reset_trace_context,
    set_trace_context,
)
from core.config import settings


def test_langchain_config_is_disabled_without_credentials(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(settings, "langfuse_tracing_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", None)
    monkeypatch.setattr(settings, "langfuse_secret_key", None)

    token = set_trace_context(AgentTraceContext(run_id="run-1", user_id=7))
    try:
        assert langchain_config("reasoner-decide") is None
    finally:
        reset_trace_context(token)


def test_langchain_config_includes_trace_attributes(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(settings, "langfuse_tracing_enabled", True)
    monkeypatch.setattr(settings, "langfuse_public_key", "pk-lf-test")
    monkeypatch.setattr(settings, "langfuse_secret_key", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

    token = set_trace_context(
        AgentTraceContext(run_id="run-1", user_id=7, session_id="chat-42")
    )
    try:
        config = langchain_config(
            "reasoner-decide",
            extra_metadata={"tool_count": 5},
        )
    finally:
        reset_trace_context(token)

    assert config is not None
    assert config["run_name"] == "agent-reasoner-decide"
    assert len(config["callbacks"]) == 1
    assert config["metadata"] == {
        "agent_run_id": "run-1",
        "agent_operation": "reasoner-decide",
        "langfuse_tags": ["agent", "react"],
        "langfuse_user_id": "7",
        "langfuse_session_id": "chat-42",
        "tool_count": 5,
    }
