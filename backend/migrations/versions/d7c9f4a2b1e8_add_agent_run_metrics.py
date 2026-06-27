"""add_agent_run_metrics

Revision ID: d7c9f4a2b1e8
Revises: b20b64c51624
Create Date: 2026-06-25 17:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "d7c9f4a2b1e8"
down_revision: str | Sequence[str] | None = "b20b64c51624"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_run_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("chat_session_id", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("iterations", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column(
            "termination_reason",
            sqlmodel.sql.sqltypes.AutoString(length=64),
            nullable=False,
        ),
        sa.Column("streamed", sa.Boolean(), nullable=False),
        sa.Column("llm_call_count", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cost_usd >= 0", name="ck_agent_run_cost_usd"),
        sa.CheckConstraint("duration_ms >= 0", name="ck_agent_run_duration_ms"),
        sa.CheckConstraint("iterations >= 0", name="ck_agent_run_iterations"),
        sa.CheckConstraint(
            "llm_call_count >= 0",
            name="ck_agent_run_llm_call_count",
        ),
        sa.CheckConstraint("total_tokens >= 0", name="ck_agent_run_total_tokens"),
        sa.ForeignKeyConstraint(["chat_session_id"], ["chat_sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_run_metrics_active_occurred_at",
        "agent_run_metrics",
        ["occurred_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        op.f("ix_agent_run_metrics_chat_session_id"),
        "agent_run_metrics",
        ["chat_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_run_metrics_occurred_at",
        "agent_run_metrics",
        ["occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_agent_run_metrics_run_id",
        "agent_run_metrics",
        ["run_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_agent_run_metrics_user_id"),
        "agent_run_metrics",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_agent_run_metrics_user_occurred_at",
        "agent_run_metrics",
        ["user_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_agent_run_metrics_user_occurred_at", table_name="agent_run_metrics")
    op.drop_index(op.f("ix_agent_run_metrics_user_id"), table_name="agent_run_metrics")
    op.drop_index("ix_agent_run_metrics_run_id", table_name="agent_run_metrics")
    op.drop_index("ix_agent_run_metrics_occurred_at", table_name="agent_run_metrics")
    op.drop_index(
        op.f("ix_agent_run_metrics_chat_session_id"),
        table_name="agent_run_metrics",
    )
    op.drop_index(
        "ix_agent_run_metrics_active_occurred_at",
        table_name="agent_run_metrics",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("agent_run_metrics")
