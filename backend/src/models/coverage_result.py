from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field

from .base import BaseModel


class CoverageResultModel(BaseModel, table=True):
    __tablename__ = "coverage_results"

    mission_id: int | None = Field(
        default=None, foreign_key="missions.id", nullable=True
    )
    flight_path_id: int | None = Field(
        default=None, foreign_key="flight_paths.id", nullable=True
    )
    coverage_percent: float | None = Field(default=None)
    details: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column("details", JSON, nullable=True),
    )
