from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, Column, DateTime, Index
from sqlmodel import Field

from .base import BaseModel, get_utc_now


class TelemetryModel(BaseModel, table=True):
    __tablename__ = "telemetry"
    __table_args__ = (
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="ck_telemetry_latitude",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="ck_telemetry_longitude",
        ),
        CheckConstraint(
            "velocity IS NULL OR velocity >= 0",
            name="ck_telemetry_velocity",
        ),
        CheckConstraint(
            "heading IS NULL OR (heading >= 0 AND heading < 360)",
            name="ck_telemetry_heading",
        ),
        Index("ix_telemetry_iot_node_id_timestamp", "iot_node_id", "timestamp"),
    )

    iot_node_id: int = Field(
        foreign_key="iot_nodes.id",
        nullable=False,
        index=True,
    )
    timestamp: datetime = Field(
        default_factory=get_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    altitude: float | None = Field(default=None)
    velocity: float | None = Field(default=None, ge=0)
    heading: float | None = Field(default=None, ge=0, lt=360)
    data: dict[str, float] | None = Field(
        default=None,
        sa_column=Column("data", JSON, nullable=True),
    )
