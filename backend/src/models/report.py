from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field

from .base import BaseModel


class ReportModel(BaseModel, table=True):
    __tablename__ = "reports"

    mission_id: int | None = Field(
        default=None, foreign_key="missions.id", nullable=True
    )
    author_id: int | None = Field(default=None, foreign_key="users.id", nullable=True)
    title: str | None = Field(default=None)
    content: str | None = Field(default=None)
    summary: str | None = Field(default=None)
    attachments: list[str] | None = Field(
        default=None,
        sa_column=Column("attachments", JSON, nullable=True),
    )
    published_at: datetime | None = Field(default=None)
