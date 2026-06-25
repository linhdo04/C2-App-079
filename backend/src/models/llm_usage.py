from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, Index, text
from sqlmodel import Field

from .base import BaseModel, get_utc_now


class LLMUsageEventModel(BaseModel, table=True):
    __tablename__ = "llm_usage_events"
    __table_args__ = (
        CheckConstraint("input_tokens >= 0", name="ck_llm_usage_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="ck_llm_usage_output_tokens"),
        CheckConstraint("total_tokens >= 0", name="ck_llm_usage_total_tokens"),
        CheckConstraint("cost_usd >= 0", name="ck_llm_usage_cost_usd"),
        Index("ix_llm_usage_occurred_at", "occurred_at"),
        Index("ix_llm_usage_user_occurred_at", "user_id", "occurred_at"),
        Index("ix_llm_usage_run_id", "run_id"),
        Index(
            "ix_llm_usage_active_occurred_at",
            "occurred_at",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    user_id: int | None = Field(
        default=None,
        foreign_key="users.id",
        nullable=True,
        index=True,
    )
    chat_session_id: int | None = Field(
        default=None,
        foreign_key="chat_sessions.id",
        nullable=True,
        index=True,
    )
    run_id: str | None = Field(default=None, max_length=64, nullable=True)
    operation: str = Field(max_length=120, nullable=False)
    model_name: str = Field(max_length=120, nullable=False)
    input_tokens: int = Field(default=0, ge=0, nullable=False)
    output_tokens: int = Field(default=0, ge=0, nullable=False)
    total_tokens: int = Field(default=0, ge=0, nullable=False)
    cache_read_tokens: int = Field(default=0, ge=0, nullable=False)
    reasoning_tokens: int = Field(default=0, ge=0, nullable=False)
    cost_usd: float = Field(default=0, ge=0, nullable=False)
    usage_metadata: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column("usage_metadata", JSON, nullable=True),
    )
    occurred_at: datetime = Field(
        default_factory=get_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class CostBudgetModel(BaseModel, table=True):
    __tablename__ = "cost_budgets"
    __table_args__ = (
        CheckConstraint("monthly_budget_usd >= 0", name="ck_cost_budgets_monthly"),
        CheckConstraint(
            "alert_threshold_percent BETWEEN 1 AND 100",
            name="ck_cost_budgets_alert_threshold",
        ),
    )

    monthly_budget_usd: float = Field(default=0, ge=0, nullable=False)
    alert_threshold_percent: int = Field(default=80, ge=1, le=100, nullable=False)
