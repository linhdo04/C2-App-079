from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, DateTime, Index, String, text
from sqlmodel import Field

from .base import BaseModel


class MissionStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MissionModel(BaseModel, table=True):
    __tablename__ = "missions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'in_progress', 'completed', 'cancelled')",
            name="ck_missions_status",
        ),
        CheckConstraint(
            "ended_at IS NULL OR started_at IS NULL OR ended_at >= started_at",
            name="ck_missions_date_order",
        ),
        Index(
            "ix_missions_active_owner_id",
            "owner_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: str = Field(nullable=False)
    description: str | None = Field(default=None)
    owner_id: int | None = Field(
        default=None,
        foreign_key="users.id",
        nullable=True,
        index=True,
    )
    status: MissionStatus = Field(
        default=MissionStatus.PLANNED,
        sa_type=String,
        nullable=False,
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    ended_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
