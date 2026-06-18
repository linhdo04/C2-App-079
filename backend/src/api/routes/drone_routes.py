from datetime import datetime
from secrets import token_urlsafe
from typing import Annotated, Any, Self, cast

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user
from api.responses import DataResponse
from core.security import hash_secret, verify_secret
from infrastructure.database.postgres import get_session
from models.iot_node import IoTNodeModel
from models.mission import MissionModel
from models.telemetry import TelemetryModel
from models.user import UserModel

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


class DroneApiKeyPublic(BaseModel):
    iot_node_id: int
    api_key: str


async def require_drone_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    if x_api_key is None or x_api_key == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid drone API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key


def _verify_node_api_key(node: IoTNodeModel, api_key: str) -> None:
    if not verify_secret(api_key, node.api_key_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid drone API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )


@router.post(
    "/nodes/{iot_node_id}/api-key",
    response_model=DataResponse[DroneApiKeyPublic],
)
async def create_drone_api_key(
    iot_node_id: int,
    current_user: Annotated[UserModel, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataResponse[DroneApiKeyPublic]:
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    node = await _get_owned_active_iot_node(session, iot_node_id, current_user.id)
    api_key = f"drn_{token_urlsafe(32)}"
    node.api_key_hash = hash_secret(api_key)
    await session.flush()

    return DataResponse(
        data=DroneApiKeyPublic(
            iot_node_id=iot_node_id,
            api_key=api_key,
        )
    )


@router.post(
    "/telemetry",
    response_model=DataResponse[DroneTelemetryPublic],
    status_code=status.HTTP_201_CREATED,
)
async def ingest_drone_telemetry(
    req: DroneTelemetryCreate,
    api_key: Annotated[str, Depends(require_drone_api_key)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataResponse[DroneTelemetryPublic]:
    node = await _get_active_iot_node(session, req)
    _verify_node_api_key(node, api_key)
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


async def _get_owned_active_iot_node(
    session: AsyncSession,
    iot_node_id: int,
    user_id: int,
) -> IoTNodeModel:
    result = await session.execute(
        select(IoTNodeModel)
        .join(
            MissionModel,
            cast(Any, IoTNodeModel.mission_id == MissionModel.id),
        )
        .where(
            cast(ColumnElement[bool], IoTNodeModel.id == iot_node_id),
            cast(ColumnElement[bool], MissionModel.owner_id == user_id),
            cast(ColumnElement[bool], cast(Any, IoTNodeModel.deleted_at).is_(None)),
            cast(ColumnElement[bool], cast(Any, MissionModel.deleted_at).is_(None)),
        )
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="IoT node not found",
        )
    return node


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
