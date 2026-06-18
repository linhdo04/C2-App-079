from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException

from api.routes.drone_routes import (
    DroneTelemetryCreate,
    create_drone_api_key,
    ingest_drone_telemetry,
    require_drone_api_key,
)
from core.security import hash_secret, verify_secret
from models.iot_node import IoTNodeModel
from models.telemetry import TelemetryModel
from models.user import UserModel


class FakeResult:
    def __init__(self, node: IoTNodeModel | None) -> None:
        self.node = node

    def scalar_one_or_none(self) -> IoTNodeModel | None:
        return self.node


class FakeSession:
    def __init__(self, node: IoTNodeModel | None) -> None:
        self.node = node
        self.statements: list[Any] = []
        self.added_telemetry: TelemetryModel | None = None
        self.flush_calls = 0

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.node)

    def add(self, telemetry: TelemetryModel) -> None:
        self.added_telemetry = telemetry

    async def flush(self) -> None:
        self.flush_calls += 1
        if self.added_telemetry is not None:
            self.added_telemetry.id = 42

    async def refresh(self, telemetry: TelemetryModel) -> None:
        return None


def user_factory(user_id: int | None = 11) -> UserModel:
    return UserModel(
        id=user_id,
        name="Drone Owner",
        email="drone-owner@example.com",
        password_hash="hash",
    )


def node_factory(*, api_key: str = "node-secret") -> IoTNodeModel:
    return IoTNodeModel(
        id=7,
        name="Drone Alpha",
        serial_number="DRONE-001",
        mission_id=3,
        api_key_hash=hash_secret(api_key),
    )


@pytest.mark.asyncio
async def test_create_drone_api_key_rotates_key_for_owned_node() -> None:
    node = node_factory(api_key="old-secret")
    old_hash = node.api_key_hash
    session = FakeSession(node)

    response = await create_drone_api_key(
        7,
        user_factory(),
        session,  # type: ignore[arg-type]
    )

    assert response.data.iot_node_id == 7
    assert response.data.api_key.startswith("drn_")
    assert response.data.api_key != old_hash
    assert node.api_key_hash is not None
    assert node.api_key_hash != old_hash
    assert verify_secret(response.data.api_key, node.api_key_hash)
    assert session.flush_calls == 1
    statement = str(session.statements[0])
    assert "JOIN missions" in statement
    assert "missions.owner_id" in statement
    assert "iot_nodes.deleted_at IS NULL" in statement
    assert "missions.deleted_at IS NULL" in statement


@pytest.mark.asyncio
async def test_create_drone_api_key_rejects_user_without_id() -> None:
    session = FakeSession(node_factory())

    with pytest.raises(HTTPException) as exc_info:
        await create_drone_api_key(
            7,
            user_factory(None),
            session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 401
    assert session.statements == []
    assert session.flush_calls == 0


@pytest.mark.asyncio
async def test_create_drone_api_key_rejects_missing_or_unowned_node() -> None:
    session = FakeSession(None)

    with pytest.raises(HTTPException) as exc_info:
        await create_drone_api_key(
            999,
            user_factory(),
            session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 404
    assert session.flush_calls == 0


@pytest.mark.asyncio
async def test_require_drone_api_key_accepts_present_key() -> None:
    assert await require_drone_api_key("secret") == "secret"


@pytest.mark.asyncio
@pytest.mark.parametrize("api_key", [None, ""])
async def test_require_drone_api_key_rejects_missing_key(api_key: str | None) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_drone_api_key(api_key)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_ingest_drone_telemetry_saves_sample_and_updates_node() -> None:
    timestamp = datetime(2026, 6, 17, 8, 30, tzinfo=UTC)
    node = node_factory(api_key="node-secret")
    session = FakeSession(node)
    request = DroneTelemetryCreate(
        serial_number="DRONE-001",
        timestamp=timestamp,
        latitude=10.5,
        longitude=106.7,
        altitude=120.0,
        velocity=8.5,
        heading=45.0,
        temperature_celsius=31.2,
        humidity_percent=70.0,
        data={"battery_percent": 86.0},
    )

    response = await ingest_drone_telemetry(
        request,
        "node-secret",
        session,  # type: ignore[arg-type]
    )

    assert response.data.id == 42
    assert response.data.iot_node_id == 7
    assert response.data.timestamp == timestamp
    assert session.added_telemetry is not None
    assert session.added_telemetry.iot_node_id == 7
    assert session.added_telemetry.latitude == 10.5
    assert session.added_telemetry.longitude == 106.7
    assert session.added_telemetry.data == {"battery_percent": 86.0}
    assert node.last_seen == timestamp
    assert node.latitude == 10.5
    assert node.longitude == 106.7
    assert "iot_nodes.serial_number" in str(session.statements[0])
    assert "iot_nodes.deleted_at IS NULL" in str(session.statements[0])


@pytest.mark.asyncio
async def test_ingest_drone_telemetry_rejects_mismatched_node_key() -> None:
    session = FakeSession(node_factory(api_key="node-secret"))
    request = DroneTelemetryCreate(iot_node_id=7, latitude=10.5)

    with pytest.raises(HTTPException) as exc_info:
        await ingest_drone_telemetry(
            request,
            "other-secret",
            session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 401
    assert session.added_telemetry is None


@pytest.mark.asyncio
async def test_ingest_drone_telemetry_rejects_unconfigured_node_key() -> None:
    node = node_factory()
    node.api_key_hash = None
    session = FakeSession(node)
    request = DroneTelemetryCreate(iot_node_id=7, latitude=10.5)

    with pytest.raises(HTTPException) as exc_info:
        await ingest_drone_telemetry(
            request,
            "node-secret",
            session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 401
    assert session.added_telemetry is None


@pytest.mark.asyncio
async def test_ingest_drone_telemetry_rejects_unknown_node() -> None:
    session = FakeSession(None)
    request = DroneTelemetryCreate(iot_node_id=999, latitude=10.5)

    with pytest.raises(HTTPException) as exc_info:
        await ingest_drone_telemetry(
            request,
            "node-secret",
            session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 404
    assert session.added_telemetry is None
