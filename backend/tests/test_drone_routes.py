from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException

from api.routes.drone_routes import (
    DroneTelemetryCreate,
    ingest_drone_telemetry,
    require_drone_api_key,
)
from models.iot_node import IoTNodeModel
from models.telemetry import TelemetryModel


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

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.node)

    def add(self, telemetry: TelemetryModel) -> None:
        self.added_telemetry = telemetry

    async def flush(self) -> None:
        if self.added_telemetry is not None:
            self.added_telemetry.id = 42

    async def refresh(self, telemetry: TelemetryModel) -> None:
        return None


def node_factory() -> IoTNodeModel:
    return IoTNodeModel(
        id=7,
        name="Drone Alpha",
        serial_number="DRONE-001",
        mission_id=3,
    )


@pytest.mark.asyncio
async def test_require_drone_api_key_accepts_configured_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("api.routes.drone_routes.settings.drone_api_key", "secret")

    await require_drone_api_key("secret")


@pytest.mark.asyncio
async def test_require_drone_api_key_rejects_missing_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("api.routes.drone_routes.settings.drone_api_key", None)

    with pytest.raises(HTTPException) as exc_info:
        await require_drone_api_key("secret")

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_require_drone_api_key_rejects_invalid_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("api.routes.drone_routes.settings.drone_api_key", "secret")

    with pytest.raises(HTTPException) as exc_info:
        await require_drone_api_key("wrong")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_ingest_drone_telemetry_saves_sample_and_updates_node() -> None:
    timestamp = datetime(2026, 6, 17, 8, 30, tzinfo=UTC)
    node = node_factory()
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
        None,
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
async def test_ingest_drone_telemetry_rejects_unknown_node() -> None:
    session = FakeSession(None)
    request = DroneTelemetryCreate(iot_node_id=999, latitude=10.5)

    with pytest.raises(HTTPException) as exc_info:
        await ingest_drone_telemetry(
            request,
            None,
            session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 404
    assert session.added_telemetry is None
