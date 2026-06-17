from datetime import datetime
from secrets import compare_digest
from typing import Annotated, Any, Self, cast

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.responses import DataResponse
from core import settings
from infrastructure.database.postgres import get_session
from models.iot_node import IoTNodeModel
from models.telemetry import TelemetryModel

router = APIRouter(prefix="/drones", tags=["drones"])


class DroneTelemetryCreate(BaseModel):
    iot_node_id: int | None = Field(default=None, gt=0)
    serial_number: str | None = Field(default=None, min_length=1, max_length=255)
    timestamp: datetime | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    altitude: float | None = None
    velocity: float | None = Field(default=None, ge=0)
    heading: float | None = Field(default=None, ge=0, lt=360)
    temperature_celsius: float | None = Field(default=None, ge=-273.15)
    humidity_percent: float | None = Field(default=None, ge=0, le=100)
    data: dict[str, float] | None = None

    @model_validator(mode="after")
    def require_node_identifier(self) -> Self:
        if self.iot_node_id is None and self.serial_number is None:
            raise ValueError("iot_node_id or serial_number is required")
        return self


class DroneTelemetryPublic(BaseModel):
    id: int
    iot_node_id: int
    timestamp: datetime


async def require_drone_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    if not settings.drone_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Drone ingestion is not configured",
        )
    if x_api_key is None or not compare_digest(x_api_key, settings.drone_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid drone API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


@router.post(
    "/telemetry",
    response_model=DataResponse[DroneTelemetryPublic],
    status_code=status.HTTP_201_CREATED,
)
async def ingest_drone_telemetry(
    req: DroneTelemetryCreate,
    _api_key: Annotated[None, Depends(require_drone_api_key)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataResponse[DroneTelemetryPublic]:
    node = await _get_active_iot_node(session, req)
    node_id = cast(int, node.id)
    telemetry_data = req.model_dump(exclude={"serial_number", "iot_node_id"})
    if req.timestamp is None:
        telemetry_data.pop("timestamp")
    telemetry = TelemetryModel(iot_node_id=node_id, **telemetry_data)

    node.last_seen = telemetry.timestamp
    if req.latitude is not None:
        node.latitude = req.latitude
    if req.longitude is not None:
        node.longitude = req.longitude

    session.add(telemetry)
    await session.flush()
    await session.refresh(telemetry)

    if telemetry.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Telemetry was not persisted",
        )
    return DataResponse(
        data=DroneTelemetryPublic(
            id=telemetry.id,
            iot_node_id=telemetry.iot_node_id,
            timestamp=telemetry.timestamp,
        )
    )


async def _get_active_iot_node(
    session: AsyncSession,
    req: DroneTelemetryCreate,
) -> IoTNodeModel:
    statement = select(IoTNodeModel).where(
        cast(ColumnElement[bool], cast(Any, IoTNodeModel.deleted_at).is_(None)),
    )
    if req.iot_node_id is not None:
        statement = statement.where(
            cast(ColumnElement[bool], IoTNodeModel.id == req.iot_node_id)
        )
    else:
        statement = statement.where(
            cast(ColumnElement[bool], IoTNodeModel.serial_number == req.serial_number)
        )

    result = await session.execute(statement)
    node = result.scalar_one_or_none()
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="IoT node not found",
        )
    if node.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="IoT node is missing an id",
        )
    return node
