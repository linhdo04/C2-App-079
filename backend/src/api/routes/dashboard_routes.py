from datetime import UTC, datetime, time, timedelta
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user
from api.responses import CollectionMeta, CollectionResponse
from infrastructure.database.postgres import get_session
from models.base import get_utc_now
from models.iot_node import IoTNodeModel
from models.mission import MissionModel
from models.telemetry import TelemetryModel
from models.user import UserModel

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
LOCAL_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


class TelemetryReadingPublic(BaseModel):
    timestamp: datetime
    temperature_celsius: float | None
    humidity_percent: float | None
    node_name: str
    mission_name: str


class TelemetryMeta(CollectionMeta):
    latest_timestamp: datetime | None


class TelemetryListResponse(CollectionResponse[TelemetryReadingPublic]):
    meta: TelemetryMeta


@router.get("/telemetry", response_model=TelemetryListResponse)
async def list_environment_telemetry(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TelemetryListResponse:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    start_of_day, start_of_next_day = _current_local_day_utc_range()
    statement = (
        select(
            TelemetryModel,
            cast(Any, IoTNodeModel.name),
            cast(Any, MissionModel.name),
        )
        .join(
            IoTNodeModel,
            cast(Any, TelemetryModel.iot_node_id == IoTNodeModel.id),
        )
        .join(
            MissionModel,
            cast(Any, IoTNodeModel.mission_id == MissionModel.id),
        )
        .where(
            cast(ColumnElement[bool], MissionModel.owner_id == current_user.id),
            cast(
                ColumnElement[bool],
                cast(Any, MissionModel.deleted_at).is_(None),
            ),
            cast(
                ColumnElement[bool],
                cast(Any, IoTNodeModel.deleted_at).is_(None),
            ),
            cast(
                ColumnElement[bool],
                cast(Any, TelemetryModel.deleted_at).is_(None),
            ),
            cast(
                ColumnElement[bool],
                cast(Any, TelemetryModel.timestamp) >= start_of_day,
            ),
            cast(
                ColumnElement[bool],
                cast(Any, TelemetryModel.timestamp) < start_of_next_day,
            ),
            or_(
                cast(Any, TelemetryModel.temperature_celsius).is_not(None),
                cast(Any, TelemetryModel.humidity_percent).is_not(None),
            ),
        )
        .order_by(
            cast(Any, TelemetryModel.timestamp).desc(),
            cast(Any, TelemetryModel.id).desc(),
        )
    )
    result = await session.execute(statement)

    readings = [
        TelemetryReadingPublic(
            timestamp=telemetry.timestamp,
            temperature_celsius=telemetry.temperature_celsius,
            humidity_percent=telemetry.humidity_percent,
            node_name=node_name,
            mission_name=mission_name,
        )
        for telemetry, node_name, mission_name in result.all()
    ]
    readings.reverse()
    return TelemetryListResponse(
        data=readings,
        meta=TelemetryMeta(
            count=len(readings),
            latest_timestamp=readings[-1].timestamp if readings else None,
        ),
    )


def _current_local_day_utc_range() -> tuple[datetime, datetime]:
    current = get_utc_now().astimezone(LOCAL_TIMEZONE)
    start = datetime.combine(current.date(), time.min, tzinfo=LOCAL_TIMEZONE)
    end = start + timedelta(days=1)
    return start.astimezone(UTC), end.astimezone(UTC)
