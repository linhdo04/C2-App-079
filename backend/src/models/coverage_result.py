from typing import Any

from sqlalchemy import JSON, CheckConstraint, Column
from sqlmodel import Field

from .base import BaseModel


class CoverageResultModel(BaseModel, table=True):
    __tablename__ = "coverage_results"
    __table_args__ = (
        CheckConstraint(
            "coverage_percent IS NULL OR coverage_percent BETWEEN 0 AND 100",
            name="ck_coverage_results_percent",
        ),
    )

    mission_id: int | None = Field(
        default=None,
        foreign_key="missions.id",
        nullable=True,
        index=True,
    )
    flight_path_id: int | None = Field(
        default=None,
        foreign_key="flight_paths.id",
        nullable=True,
        index=True,
    )
    coverage_percent: float | None = Field(default=None, ge=0, le=100)
    details: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column("details", JSON, nullable=True),
    )
