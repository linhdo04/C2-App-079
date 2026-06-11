from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import DateTime, func
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

TIMEZONE_AWARE_DATETIME = cast(type[Any], DateTime(timezone=True))


def get_utc_now() -> datetime:
    return datetime.now(UTC)


class BaseModel(SQLModel):
    model_config = SQLModelConfig(
        from_attributes=True,
        validate_assignment=True,
    )

    id: int | None = Field(default=None, primary_key=True)

    created_at: datetime = Field(
        default_factory=get_utc_now,
        sa_type=TIMEZONE_AWARE_DATETIME,
        sa_column_kwargs={"server_default": func.now()},
        nullable=False,
    )

    updated_at: datetime = Field(
        default_factory=get_utc_now,
        sa_type=TIMEZONE_AWARE_DATETIME,
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()},
        nullable=False,
    )

    deleted_at: datetime | None = Field(
        default=None,
        sa_type=TIMEZONE_AWARE_DATETIME,
        nullable=True,
    )
