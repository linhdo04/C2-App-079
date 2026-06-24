"""LLM usage capture for local cost management."""

from typing import Any

import structlog

from core import settings
from infrastructure.database.postgres import db_session
from models.llm_usage import LLMUsageEventModel

from .pricing import estimate_cost_usd
from .tracing import current_trace_context

logger = structlog.get_logger(__name__)


def _token_count(usage: dict[str, Any], key: str) -> int:
    value = usage.get(key, 0)
    return value if isinstance(value, int) and value >= 0 else 0


def _nested_token_count(
    usage: dict[str, Any],
    section: str,
    key: str,
) -> int:
    value = usage.get(section)
    if not isinstance(value, dict):
        return 0
    return _token_count(value, key)


def _model_name(response: Any) -> str:
    response_metadata = getattr(response, "response_metadata", None)
    if isinstance(response_metadata, dict):
        for key in ("model_name", "model", "model_version"):
            value = response_metadata.get(key)
            if isinstance(value, str) and value:
                return value
    value = getattr(response, "model_name", None)
    if isinstance(value, str) and value:
        return value
    return settings.default_model


async def record_llm_usage(
    response: Any,
    *,
    operation: str,
) -> None:
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        return

    usage_data = dict(usage)
    input_tokens = _token_count(usage_data, "input_tokens")
    output_tokens = _token_count(usage_data, "output_tokens")
    total_tokens = _token_count(usage_data, "total_tokens")
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    cache_read_tokens = _nested_token_count(
        usage_data,
        "input_token_details",
        "cache_read",
    )
    reasoning_tokens = _nested_token_count(
        usage_data,
        "output_token_details",
        "reasoning",
    )
    model_name = _model_name(response)

    context = current_trace_context()
    chat_session_id: int | None = None
    if context is not None and context.session_id is not None:
        try:
            chat_session_id = int(context.session_id)
        except ValueError:
            chat_session_id = None

    event = LLMUsageEventModel(
        user_id=context.user_id if context is not None else None,
        chat_session_id=chat_session_id,
        run_id=context.run_id if context is not None else None,
        operation=operation,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cache_read_tokens=cache_read_tokens,
        reasoning_tokens=reasoning_tokens,
        cost_usd=estimate_cost_usd(
            input_tokens,
            output_tokens,
            cache_read_tokens=cache_read_tokens,
            model_name=model_name,
        ),
        usage_metadata=usage_data,
    )

    try:
        async with db_session() as session:
            session.add(event)
    except RuntimeError:
        logger.warning("llm_usage_capture_skipped", operation=operation)
    except Exception as exc:  # pragma: no cover - best-effort observability path
        logger.warning(
            "llm_usage_capture_failed",
            operation=operation,
            error_type=type(exc).__name__,
        )
