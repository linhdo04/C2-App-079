from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field

from .base import BaseModel


class IoTNodeModel(BaseModel, table=True):
    __tablename__ = "iot_nodes"

    name: str = Field(nullable=False)
    node_type: str | None = Field(default=None)
    serial_number: str | None = Field(default=None, unique=True)
    mission_id: int | None = Field(
        default=None, foreign_key="missions.id", nullable=True
    )
    latitude: float | None = Field(default=None)
    longitude: float | None = Field(default=None)
    last_seen: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    node_metadata: dict[str, Any] | None = Field(
        default=None, sa_column=Column("metadata", JSON, nullable=True)
    )
