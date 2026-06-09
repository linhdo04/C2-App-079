from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field

from .base import BaseModel


class FlightPathModel(BaseModel, table=True):
    __tablename__ = "flight_paths"

    mission_id: int | None = Field(
        default=None, foreign_key="missions.id", nullable=True
    )
    name: str | None = Field(default=None)
    path: list[dict[str, Any]] | None = Field(
        default_factory=list,
        sa_column=Column("path", JSON, nullable=True),
    )
    total_distance_m: float | None = Field(default=None)
    estimated_duration_s: int | None = Field(default=None)
    flown: bool = Field(default=False, nullable=False)
