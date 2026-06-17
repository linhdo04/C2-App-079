"""Langfuse tracing helpers for the production agent."""

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from core.config import settings


@dataclass(frozen=True)
class AgentTraceContext:
    run_id: str
    user_id: int | None = None
    session_id: str | None = None


_current_trace_context: ContextVar[AgentTraceContext | None] = ContextVar(
    "agent_trace_context",
    default=None,
)
_langfuse_client: Any | None = None


def langfuse_enabled() -> bool:
    return bool(
        settings.langfuse_tracing_enabled
        and settings.langfuse_public_key
        and settings.langfuse_secret_key
    )


def _get_langfuse_client() -> Any:
    global _langfuse_client
    if _langfuse_client is None:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_base_url,
            tracing_enabled=settings.langfuse_tracing_enabled,
            environment=settings.app_env,
        )
    return _langfuse_client


def set_trace_context(context: AgentTraceContext) -> Any:
    return _current_trace_context.set(context)


def reset_trace_context(token: Any) -> None:
    _current_trace_context.reset(token)


def current_trace_context() -> AgentTraceContext | None:
    return _current_trace_context.get()


def _metadata(
    operation: str,
    context: AgentTraceContext,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "agent_run_id": context.run_id,
        "agent_operation": operation,
        "langfuse_tags": ["agent", "react"],
    }
    if context.user_id is not None:
        metadata["langfuse_user_id"] = str(context.user_id)
    if context.session_id is not None:
        metadata["langfuse_session_id"] = context.session_id
    if extra:
        metadata.update(extra)
    return metadata


def langchain_config(
    operation: str,
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    context = current_trace_context()
    if context is None or not langfuse_enabled():
        return None

    from langfuse.langchain import CallbackHandler

    _get_langfuse_client()
    return {
        "callbacks": [CallbackHandler()],
        "metadata": _metadata(operation, context, extra=extra_metadata),
        "run_name": f"agent-{operation}",
    }


@contextmanager
def agent_run_observation(
    context: AgentTraceContext,
    *,
    question: str,
) -> Iterator[Any]:
    if not langfuse_enabled():
        yield None
        return

    from langfuse import propagate_attributes

    langfuse = _get_langfuse_client()
    with langfuse.start_as_current_observation(
        as_type="span",
        name="agent-run",
    ) as span:
        span.update(
            input={"question": question},
            metadata=_metadata("run", context),
        )
        with propagate_attributes(
            trace_name="agent-run",
            user_id=str(context.user_id) if context.user_id is not None else None,
            session_id=context.session_id,
            tags=["agent", "react"],
        ):
            yield span


@contextmanager
def agent_span(
    name: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any]:
    context = current_trace_context()
    if context is None or not langfuse_enabled():
        yield None
        return

    with _get_langfuse_client().start_as_current_observation(
        as_type="span",
        name=name,
    ) as span:
        span.update(metadata=_metadata(name, context, extra=metadata))
        yield span


def null_observation() -> Any:
    return nullcontext()


__all__ = [
    "AgentTraceContext",
    "agent_run_observation",
    "agent_span",
    "current_trace_context",
    "langchain_config",
    "langfuse_enabled",
    "reset_trace_context",
    "set_trace_context",
]
