from typing import Any

from sqlalchemy import JSON, CheckConstraint, Column
from sqlmodel import Field

from .base import BaseModel


class FlightPathModel(BaseModel, table=True):
    __tablename__ = "flight_paths"
    __table_args__ = (
        CheckConstraint(
            "total_distance_m IS NULL OR total_distance_m >= 0",
            name="ck_flight_paths_total_distance",
        ),
        CheckConstraint(
            "estimated_duration_s IS NULL OR estimated_duration_s >= 0",
            name="ck_flight_paths_estimated_duration",
        ),
    )

    mission_id: int | None = Field(
        default=None,
        foreign_key="missions.id",
        nullable=True,
        index=True,
    )
    name: str | None = Field(default=None)
    path: list[dict[str, Any]] | None = Field(
        default_factory=list,
        sa_column=Column("path", JSON, nullable=True),
    )
    total_distance_m: float | None = Field(default=None, ge=0)
    estimated_duration_s: int | None = Field(default=None, ge=0)
    flown: bool = Field(default=False, nullable=False)
