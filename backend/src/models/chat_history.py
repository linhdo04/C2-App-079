from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field

from .base import BaseModel, get_utc_now


class ChatHistoryModel(BaseModel, table=True):
    __tablename__ = "chat_histories"

    mission_id: int | None = Field(
        default=None, foreign_key="missions.id", nullable=True
    )
    user_id: int | None = Field(default=None, foreign_key="users.id", nullable=True)
    role: str = Field(default="user", nullable=False)
    message: str = Field(nullable=False)
    chat_metadata: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column("metadata", JSON, nullable=True),
    )
    timestamp: datetime = Field(
        default_factory=get_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
