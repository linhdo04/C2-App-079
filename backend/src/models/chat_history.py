from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, Index, String
from sqlmodel import Field

from .base import BaseModel, get_utc_now


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatHistoryModel(BaseModel, table=True):
    __tablename__ = "chat_histories"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system', 'tool')",
            name="ck_chat_histories_role",
        ),
        Index(
            "ix_chat_histories_mission_id_timestamp",
            "mission_id",
            "timestamp",
        ),
    )

    mission_id: int | None = Field(
        default=None,
        foreign_key="missions.id",
        nullable=True,
        index=True,
    )
    user_id: int | None = Field(
        default=None,
        foreign_key="users.id",
        nullable=True,
        index=True,
    )
    role: ChatRole = Field(
        default=ChatRole.USER,
        sa_type=String,
        nullable=False,
    )
    message: str = Field(nullable=False)
    chat_metadata: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column("metadata", JSON, nullable=True),
    )
    timestamp: datetime = Field(
        default_factory=get_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
