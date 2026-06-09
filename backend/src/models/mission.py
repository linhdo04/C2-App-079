from datetime import datetime

from sqlalchemy import Column, DateTime
from sqlmodel import Field

from .base import BaseModel


class MissionModel(BaseModel, table=True):
    __tablename__ = "missions"

    name: str = Field(nullable=False)
    description: str | None = Field(default=None)
    owner_id: int | None = Field(default=None, foreign_key="users.id", nullable=True)
    status: str = Field(default="planned", nullable=False)
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    ended_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
