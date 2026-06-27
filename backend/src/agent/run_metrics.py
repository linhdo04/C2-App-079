"""Best-effort local persistence for agent run-level metrics."""

from typing import Any, cast

import structlog
from sqlalchemy import func, select

from infrastructure.database.postgres import db_session
from models.llm_usage import AgentRunMetricModel, LLMUsageEventModel

logger = structlog.get_logger(__name__)


def _chat_session_id(session_id: str | None) -> int | None:
    if session_id is None:
        return None
    try:
        return int(session_id)
    except ValueError:
        return None


async def record_agent_run_metric(
    *,
    run_id: str,
    user_id: int | None,
    session_id: str | None,
    duration_ms: float,
    iterations: int,
    success: bool,
    termination_reason: str,
    streamed: bool,
) -> None:
    """Persist run-level metrics, aggregating local LLM usage by run_id."""

    try:
        async with db_session() as session:
            usage_result = await session.execute(
                select(
                    func.count(cast(Any, LLMUsageEventModel.id)),
                    func.coalesce(
                        func.sum(cast(Any, LLMUsageEventModel.total_tokens)), 0
                    ),
                    func.coalesce(func.sum(cast(Any, LLMUsageEventModel.cost_usd)), 0),
                ).where(cast(Any, LLMUsageEventModel.run_id) == run_id)
            )
            llm_call_count, total_tokens, cost_usd = usage_result.one()
            session.add(
                AgentRunMetricModel(
                    run_id=run_id,
                    user_id=user_id,
                    chat_session_id=_chat_session_id(session_id),
                    duration_ms=max(duration_ms, 0),
                    iterations=max(iterations, 0),
                    success=success,
                    termination_reason=termination_reason,
                    streamed=streamed,
                    llm_call_count=int(llm_call_count),
                    total_tokens=int(total_tokens),
                    cost_usd=float(cost_usd),
                )
            )
    except RuntimeError:
        logger.warning("agent_run_metric_capture_skipped", run_id=run_id)
    except Exception as exc:  # pragma: no cover - best-effort observability path
        logger.warning(
            "agent_run_metric_capture_failed",
            run_id=run_id,
            error_type=type(exc).__name__,
        )
