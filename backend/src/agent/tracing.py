"""LangSmith tracing helpers for the production agent."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from langsmith import Client

from core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentTraceContext:
    run_id: str
    user_id: int | None = None
    session_id: str | None = None


class _LangSmithObservation:
    def __init__(
        self,
        run_id: UUID,
        client: Client,
        base_metadata: dict[str, Any],
    ) -> None:
        self._run_id = run_id
        self._client = client
        self._base_metadata = base_metadata

    def update(
        self,
        *,
        metadata: dict[str, Any] | None = None,
        level: str | None = None,
        status_message: str | None = None,
        output: Any | None = None,
    ) -> None:
        extra: dict[str, Any] = {}
        if metadata is not None:
            extra["metadata"] = {**self._base_metadata, **metadata}
        if level is not None:
            extra["level"] = level
        if status_message is not None:
            extra["status_message"] = status_message

        kwargs: dict[str, Any] = {}
        if extra:
            kwargs["extra"] = extra
        if output is not None:
            kwargs["outputs"] = (
                output if isinstance(output, dict) else {"output": output}
            )
        if not kwargs:
            return

        try:
            self._client.update_run(self._run_id, **kwargs)
        except Exception as exc:  # pragma: no cover - best-effort observability
            logger.warning("langsmith_run_update_failed: %s", type(exc).__name__)


_current_trace_context: ContextVar[AgentTraceContext | None] = ContextVar(
    "agent_trace_context",
    default=None,
)
_langsmith_client: Client | None = None


def langsmith_configured() -> bool:
    return bool(settings.langsmith_api_key)


def langsmith_enabled() -> bool:
    return bool(settings.langsmith_tracing and langsmith_configured())


def _langsmith_project() -> str:
    return settings.langsmith_project or f"{settings.app_name}-{settings.app_env}-agent"


def _get_langsmith_client() -> Client:
    global _langsmith_client
    if _langsmith_client is None:
        _langsmith_client = Client(
            api_key=settings.langsmith_api_key,
            api_url=settings.langsmith_endpoint,
            workspace_id=settings.langsmith_workspace_id,
        )
    return _langsmith_client


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
        "app_env": settings.app_env,
    }
    if context.user_id is not None:
        metadata["user_id"] = str(context.user_id)
    if context.session_id is not None:
        metadata["session_id"] = context.session_id
    if extra:
        metadata.update(extra)
    return metadata


def langchain_config(
    operation: str,
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    context = current_trace_context()
    if context is None or not langsmith_enabled():
        return None

    return {
        "metadata": _metadata(operation, context, extra=extra_metadata),
        "run_name": f"agent-{operation}",
        "tags": ["agent", "react"],
    }


def _run_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        return uuid4()


@contextmanager
def agent_run_observation(
    context: AgentTraceContext,
    *,
    question: str,
) -> Iterator[Any]:
    if not langsmith_enabled():
        yield None
        return

    client = _get_langsmith_client()
    run_id = _run_id(context.run_id)
    try:
        client.create_run(
            id=run_id,
            name="agent-run",
            run_type="chain",
            inputs={"question": question},
            project_name=_langsmith_project(),
            extra={"metadata": _metadata("run", context)},
            tags=["agent", "react"],
        )
    except Exception as exc:  # pragma: no cover - best-effort observability
        logger.warning("langsmith_run_create_failed: %s", type(exc).__name__)
        yield None
        return

    try:
        yield _LangSmithObservation(run_id, client, _metadata("run", context))
    finally:
        _close_run(client, run_id)


@contextmanager
def agent_span(
    name: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any]:
    context = current_trace_context()
    if context is None or not langsmith_enabled():
        yield None
        return

    client = _get_langsmith_client()
    run_id = uuid4()
    try:
        client.create_run(
            id=run_id,
            parent_run_id=_run_id(context.run_id),
            name=name,
            run_type="chain",
            inputs={},
            project_name=_langsmith_project(),
            extra={"metadata": _metadata(name, context, extra=metadata)},
            tags=["agent", "react"],
        )
    except Exception as exc:  # pragma: no cover - best-effort observability
        logger.warning("langsmith_span_create_failed: %s", type(exc).__name__)
        yield None
        return

    try:
        yield _LangSmithObservation(
            run_id,
            client,
            _metadata(name, context, extra=metadata),
        )
    finally:
        _close_run(client, run_id)


def _close_run(client: Client, run_id: UUID) -> None:
    try:
        client.update_run(run_id, end_time=datetime.now(UTC))
    except Exception as exc:  # pragma: no cover - best-effort observability
        logger.warning("langsmith_run_close_failed: %s", type(exc).__name__)


def update_observation(
    observation: Any,
    *,
    operation: str = "observation-update",
    metadata: dict[str, Any] | None = None,
    level: str | None = None,
    status_message: str | None = None,
    output: Any | None = None,
) -> None:
    if observation is None:
        return
    kwargs: dict[str, Any] = {}
    if metadata is not None:
        context = current_trace_context()
        kwargs["metadata"] = (
            _metadata(operation, context, extra=metadata)
            if context is not None
            else metadata
        )
    if level is not None:
        kwargs["level"] = level
    if status_message is not None:
        kwargs["status_message"] = status_message
    if output is not None:
        kwargs["output"] = output
    if kwargs:
        observation.update(**kwargs)


__all__ = [
    "AgentTraceContext",
    "agent_run_observation",
    "agent_span",
    "current_trace_context",
    "langchain_config",
    "langsmith_configured",
    "langsmith_enabled",
    "reset_trace_context",
    "set_trace_context",
    "update_observation",
]
