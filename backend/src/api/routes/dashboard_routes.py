from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user
from api.responses import CollectionMeta, CollectionResponse
from infrastructure.database.postgres import get_session
from models.iot_node import IoTNodeModel
from models.mission import MissionModel
from models.telemetry import TelemetryModel
from models.user import UserModel

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class TelemetryReadingPublic(BaseModel):
    timestamp: datetime
    temperature_celsius: float | None
    humidity_percent: float | None
    node_name: str
    mission_name: str


class TelemetryMeta(CollectionMeta):
    limit: int
    latest_timestamp: datetime | None


class TelemetryListResponse(CollectionResponse[TelemetryReadingPublic]):
    meta: TelemetryMeta


@router.get("/telemetry", response_model=TelemetryListResponse)
async def list_environment_telemetry(
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
) -> TelemetryListResponse:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

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
            or_(
                cast(Any, TelemetryModel.temperature_celsius).is_not(None),
                cast(Any, TelemetryModel.humidity_percent).is_not(None),
            ),
        )
        .order_by(cast(Any, TelemetryModel.timestamp).desc())
        .limit(limit)
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
            limit=limit,
            latest_timestamp=readings[-1].timestamp if readings else None,
        ),
    )
