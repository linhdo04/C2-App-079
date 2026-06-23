from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import HTTPException

from api.routes.dashboard_routes import (
    _current_local_day_utc_range,
    list_environment_telemetry,
)
from models.telemetry import TelemetryModel
from models.user import UserModel


class FakeResult:
    def __init__(self, rows: list[tuple[TelemetryModel, str, str]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[TelemetryModel, str, str]]:
        return self.rows


class FakeSession:
    def __init__(self, rows: list[tuple[TelemetryModel, str, str]]) -> None:
        self.rows = rows
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.rows)


def user_factory(user_id: int | None = 7) -> UserModel:
    return UserModel(
        id=user_id,
        name="Dashboard User",
        email="dashboard@example.com",
        password_hash="hash",
    )


def test_current_local_day_range_uses_vietnam_timezone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api.routes.dashboard_routes.get_utc_now",
        lambda: datetime(2026, 6, 23, 4, 30, tzinfo=UTC),
    )

    start, end = _current_local_day_utc_range()

    assert start == datetime(2026, 6, 22, 17, 0, tzinfo=UTC)
    assert end == datetime(2026, 6, 23, 17, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_list_environment_telemetry_returns_current_day_chronological_user_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 6, 23, 4, 30, tzinfo=UTC)
    monkeypatch.setattr("api.routes.dashboard_routes.get_utc_now", lambda: now)
    latest = TelemetryModel(
        id=3,
        iot_node_id=3,
        timestamp=now,
        temperature_celsius=29.4,
        humidity_percent=68.0,
    )
    same_timestamp = TelemetryModel(
        id=2,
        iot_node_id=3,
        timestamp=now,
        temperature_celsius=28.8,
        humidity_percent=70.0,
    )
    earlier = TelemetryModel(
        id=1,
        iot_node_id=3,
        timestamp=now - timedelta(hours=1),
        temperature_celsius=27.1,
        humidity_percent=74.0,
    )
    session = FakeSession(
        [
            (latest, "Cảm biến 03", "Ruộng lúa"),
            (same_timestamp, "Cảm biến 03", "Ruộng lúa"),
            (earlier, "Cảm biến 03", "Ruộng lúa"),
        ]
    )

    response = await list_environment_telemetry(
        user_factory(),
        session,  # type: ignore[arg-type]
    )

    assert [reading.timestamp for reading in response.data] == [
        earlier.timestamp,
        same_timestamp.timestamp,
        latest.timestamp,
    ]
    assert [reading.temperature_celsius for reading in response.data] == [
        27.1,
        28.8,
        29.4,
    ]
    assert response.data[-1].temperature_celsius == 29.4
    assert response.data[-1].humidity_percent == 68.0
    assert response.data[-1].node_name == "Cảm biến 03"
    assert response.meta.count == 3
    assert response.meta.latest_timestamp == latest.timestamp
    statement = str(session.statements[0])
    assert "missions.owner_id" in statement
    assert "telemetry.temperature_celsius IS NOT NULL" in statement
    assert "telemetry.timestamp >= " in statement
    assert "telemetry.timestamp < " in statement
    assert "telemetry.timestamp DESC, telemetry.id DESC" in statement
    assert session.statements[0]._limit_clause is None


@pytest.mark.asyncio
async def test_list_environment_telemetry_returns_empty_list_without_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api.routes.dashboard_routes.get_utc_now",
        lambda: datetime(2026, 6, 23, 4, 30, tzinfo=UTC),
    )
    session = FakeSession([])

    response = await list_environment_telemetry(
        user_factory(),
        session,  # type: ignore[arg-type]
    )

    assert response.data == []
    assert response.meta.count == 0
    assert response.meta.latest_timestamp is None


@pytest.mark.asyncio
async def test_list_environment_telemetry_rejects_user_without_id() -> None:
    session = FakeSession([])

    with pytest.raises(HTTPException) as exc_info:
        await list_environment_telemetry(
            user_factory(None),
            session,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 401
    assert session.statements == []
