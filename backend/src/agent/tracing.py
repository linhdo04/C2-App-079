"""Metadata-safe LangSmith tracing helpers for the production agent."""

import hashlib
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

from langsmith import Client
from langsmith.run_helpers import trace

from core.config import settings

logger = logging.getLogger(__name__)

RunType = Literal["tool", "chain", "llm", "retriever", "embedding", "prompt", "parser"]


@dataclass(frozen=True)
class AgentTraceContext:
    run_id: str
    user_id: int | None = None
    session_id: str | None = None


class _LangSmithObservation:
    """Small adapter that keeps callers independent from LangSmith's RunTree."""

    def __init__(self, run: Any, base_metadata: dict[str, Any]) -> None:
        self._run = run
        self._base_metadata = base_metadata

    def update(
        self,
        *,
        metadata: dict[str, Any] | None = None,
        level: str | None = None,
        status_message: str | None = None,
        output: Any | None = None,
    ) -> None:
        merged = {**self._base_metadata, **(metadata or {})}
        if level is not None:
            merged["status_level"] = level
        if status_message is not None:
            merged["status"] = status_message
        try:
            self._run.set(metadata=merged)
            if output is not None:
                safe_output = output if isinstance(output, dict) else {"output": output}
                self._run.add_outputs(safe_output)
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
            hide_inputs=True,
            hide_outputs=True,
        )
    return _langsmith_client


def set_trace_context(context: AgentTraceContext) -> Any:
    return _current_trace_context.set(context)


def reset_trace_context(token: Any) -> None:
    _current_trace_context.reset(token)


def current_trace_context() -> AgentTraceContext | None:
    return _current_trace_context.get()


@contextmanager
def agent_trace_scope(
    *,
    user_id: int | None,
    session_id: str | None,
) -> Iterator[tuple[AgentTraceContext, bool]]:
    """Reuse an active request context or create one for direct loop calls."""

    active = current_trace_context()
    if active is not None:
        yield active, False
        return
    context = AgentTraceContext(
        run_id=str(uuid4()),
        user_id=user_id,
        session_id=session_id,
    )
    token = set_trace_context(context)
    try:
        yield context, True
    finally:
        reset_trace_context(token)


def content_metadata(value: str, *, prefix: str) -> dict[str, Any]:
    """Return useful correlation data without retaining the supplied content."""

    return {
        f"{prefix}_characters": len(value),
        f"{prefix}_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()[:16],
    }


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
        "tags": ["agent", "react", operation],
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
    streamed: bool = False,
) -> Iterator[Any]:
    """Create the request root without sending raw user content to LangSmith."""

    metadata = _metadata(
        "run",
        context,
        extra={"streamed": streamed, **content_metadata(question, prefix="input")},
    )
    with _trace_observation(
        "agent-run",
        run_type="chain",
        metadata=metadata,
        run_id=_run_id(context.run_id),
    ) as observation:
        yield observation


@contextmanager
def agent_span(
    name: str,
    *,
    metadata: dict[str, Any] | None = None,
    run_type: RunType = "chain",
) -> Iterator[Any]:
    context = current_trace_context()
    if context is None:
        yield None
        return
    base_metadata = _metadata(name, context, extra=metadata)
    with _trace_observation(
        name,
        run_type=run_type,
        metadata=base_metadata,
    ) as observation:
        yield observation


@contextmanager
def _trace_observation(
    name: str,
    *,
    run_type: RunType,
    metadata: dict[str, Any],
    run_id: UUID | None = None,
) -> Iterator[Any]:
    if not langsmith_enabled():
        yield None
        return
    try:
        manager = trace(
            name,
            run_type=run_type,
            inputs={},
            project_name=_langsmith_project(),
            tags=["agent", "react", name],
            metadata=metadata,
            client=_get_langsmith_client(),
            run_id=run_id,
        )
        run = manager.__enter__()
    except Exception as exc:  # pragma: no cover - best-effort observability
        logger.warning("langsmith_trace_failed: %s", type(exc).__name__)
        yield None
        return

    try:
        yield _LangSmithObservation(run, metadata)
    except BaseException:
        try:
            manager.__exit__(*sys.exc_info())
        except Exception as exc:  # pragma: no cover - best-effort observability
            logger.warning("langsmith_trace_close_failed: %s", type(exc).__name__)
        raise
    else:
        try:
            manager.__exit__(None, None, None)
        except Exception as exc:  # pragma: no cover - best-effort observability
            logger.warning("langsmith_trace_close_failed: %s", type(exc).__name__)


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
    safe_metadata = metadata
    if metadata is not None:
        context = current_trace_context()
        safe_metadata = (
            _metadata(operation, context, extra=metadata)
            if context is not None
            else metadata
        )
    observation.update(
        metadata=safe_metadata,
        level=level,
        status_message=status_message,
        output=output,
    )


__all__ = [
    "AgentTraceContext",
    "agent_run_observation",
    "agent_span",
    "agent_trace_scope",
    "content_metadata",
    "current_trace_context",
    "langchain_config",
    "langsmith_configured",
    "langsmith_enabled",
    "reset_trace_context",
    "set_trace_context",
    "update_observation",
]
