from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, Index, text
from sqlmodel import Field

from .base import BaseModel


class IoTNodeModel(BaseModel, table=True):
    __tablename__ = "iot_nodes"
    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="ck_iot_nodes_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="ck_iot_nodes_longitude",
        ),
        Index(
            "ix_iot_nodes_active_mission_id",
            "mission_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: str = Field(nullable=False)
    node_type: str | None = Field(default=None)
    serial_number: str | None = Field(default=None, unique=True)
    mission_id: int | None = Field(
        default=None,
        foreign_key="missions.id",
        nullable=True,
        index=True,
    )
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    last_seen: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    node_metadata: dict[str, Any] | None = Field(
        default=None, sa_column=Column("metadata", JSON, nullable=True)
    )
