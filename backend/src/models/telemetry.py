from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field

from .base import BaseModel, get_utc_now


class TelemetryModel(BaseModel, table=True):
    __tablename__ = "telemetry"

    iot_node_id: int = Field(foreign_key="iot_nodes.id", nullable=False)
    timestamp: datetime = Field(default_factory=get_utc_now, nullable=False)
    latitude: float | None = Field(default=None)
    longitude: float | None = Field(default=None)
    altitude: float | None = Field(default=None)
    velocity: float | None = Field(default=None)
    heading: float | None = Field(default=None)
    data: dict[str, float] | None = Field(
        default=None,
        sa_column=Column("data", JSON, nullable=True),
    )
