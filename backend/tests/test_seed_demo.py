from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from models.user import UserRole
from scripts.seed_demo import (
    ANOMALY_SAMPLE_COUNT,
    DEMO_ADMIN_EMAIL,
    DEMO_OPERATOR_EMAIL,
    TELEMETRY_SAMPLE_COUNT,
    TELEMETRY_SAMPLE_INTERVAL_MINUTES,
    build_telemetry_samples,
    seed_demo,
)


def test_build_telemetry_samples_creates_ordered_environment_data() -> None:
    end_time = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)

    samples = build_telemetry_samples(9, now=end_time)

    assert len(samples) == TELEMETRY_SAMPLE_COUNT
    assert samples[0].timestamp == end_time - timedelta(
        minutes=TELEMETRY_SAMPLE_INTERVAL_MINUTES * (TELEMETRY_SAMPLE_COUNT - 1)
    )
    assert samples[-1].timestamp == end_time
    assert all(
        current.timestamp - previous.timestamp
        == timedelta(minutes=TELEMETRY_SAMPLE_INTERVAL_MINUTES)
        for previous, current in zip(samples, samples[1:])
    )
    assert all(sample.iot_node_id == 9 for sample in samples)
    assert all(sample.temperature_celsius is not None for sample in samples)
    assert all(sample.humidity_percent is not None for sample in samples)
    assert samples[0].temperature_celsius != samples[-1].temperature_celsius


def test_build_telemetry_samples_places_abnormal_temperature_in_middle() -> None:
    samples = build_telemetry_samples(9, now=datetime(2026, 6, 10, tzinfo=UTC))
    anomaly_start = (TELEMETRY_SAMPLE_COUNT - ANOMALY_SAMPLE_COUNT) // 2
    anomaly_end = anomaly_start + ANOMALY_SAMPLE_COUNT

    temperatures = [sample.temperature_celsius for sample in samples]

    assert all(temperature is not None for temperature in temperatures)
    values = [cast(float, temperature) for temperature in temperatures]
    assert all(temperature < 40 for temperature in values[:anomaly_start])
    assert all(temperature >= 40 for temperature in values[anomaly_start:anomaly_end])
    assert all(temperature < 40 for temperature in values[anomaly_end:])


@pytest.mark.asyncio
async def test_seed_demo_appends_telemetry_without_deleting_existing_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.added_batches: list[list[Any]] = []

        async def execute(self, statement: Any) -> None:
            raise AssertionError(f"seed_demo must not execute a delete: {statement}")

        def add_all(self, records: list[Any]) -> None:
            self.added_batches.append(records)

        def add(self, record: Any) -> None:
            pass

    admin = SimpleNamespace(id=7)
    operator = SimpleNamespace(id=10)
    mission = SimpleNamespace(id=8)
    node = SimpleNamespace(id=9, last_seen=None)
    seeded_users: list[Any] = []
    mission_owner_ids: list[int] = []

    async def fake_user(session: Any, demo_user: Any) -> Any:
        seeded_users.append(demo_user)
        return admin if demo_user.role == UserRole.ADMIN else operator

    async def fake_mission(session: Any, user_id: int) -> Any:
        mission_owner_ids.append(user_id)
        return mission

    async def fake_node(session: Any, mission_id: int) -> Any:
        return node

    monkeypatch.setattr("scripts.seed_demo._get_or_create_user", fake_user)
    monkeypatch.setattr("scripts.seed_demo._get_or_create_mission", fake_mission)
    monkeypatch.setattr("scripts.seed_demo._get_or_create_node", fake_node)
    session = FakeSession()

    result = await seed_demo(cast(Any, session))

    assert result == (7, 10, TELEMETRY_SAMPLE_COUNT)
    assert [user.email for user in seeded_users] == [
        DEMO_ADMIN_EMAIL,
        DEMO_OPERATOR_EMAIL,
    ]
    assert [user.role for user in seeded_users] == [
        UserRole.ADMIN,
        UserRole.OPERATOR,
    ]
    assert mission_owner_ids == [10]
    assert len(session.added_batches) == 1
    assert len(session.added_batches[0]) == TELEMETRY_SAMPLE_COUNT
    assert node.last_seen == session.added_batches[0][-1].timestamp
