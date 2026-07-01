import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import hash_password
from infrastructure.database.postgres import close_db, db_session, init_db
from models.iot_node import IoTNodeModel
from models.mission import MissionModel, MissionStatus
from models.telemetry import TelemetryModel
from models.user import UserModel, UserRole

DEMO_EMAIL = "demo@aerofield.example.com"
DEMO_PASSWORD = "Demo12345!"
DEMO_MISSION_NAME = "Giám sát ruộng lúa mẫu"
DEMO_NODE_SERIAL = "DEMO-ENV-001"
TELEMETRY_SAMPLE_INTERVAL_MINUTES = 2
TELEMETRY_SAMPLE_COUNT = 24 * 60 // TELEMETRY_SAMPLE_INTERVAL_MINUTES
ANOMALY_SAMPLE_COUNT = 60 // TELEMETRY_SAMPLE_INTERVAL_MINUTES


def build_telemetry_samples(
    iot_node_id: int,
    *,
    now: datetime | None = None,
) -> list[TelemetryModel]:
    """Build one day of deterministic two-minute environmental samples."""
    end_time = now or datetime.now(UTC)
    anomaly_start = (TELEMETRY_SAMPLE_COUNT - ANOMALY_SAMPLE_COUNT) // 2
    anomaly_end = anomaly_start + ANOMALY_SAMPLE_COUNT
    samples: list[TelemetryModel] = []
    for index in range(TELEMETRY_SAMPLE_COUNT):
        timestamp = end_time - timedelta(
            minutes=TELEMETRY_SAMPLE_INTERVAL_MINUTES
            * (TELEMETRY_SAMPLE_COUNT - index - 1)
        )
        if anomaly_start <= index < anomaly_end:
            temperature = 40.0 + (index - anomaly_start) % 9 * 0.5
        else:
            temperature = 26.0 + index % 15 * 0.5
        humidity = 82.0 - index % 15 * 1.2
        samples.append(
            TelemetryModel(
                iot_node_id=iot_node_id,
                timestamp=timestamp,
                temperature_celsius=round(temperature, 1),
                humidity_percent=round(humidity, 1),
                data={"soil_moisture_percent": round(68.0 - index % 20 * 0.4, 1)},
            )
        )
    return samples


async def _get_or_create_user(session: AsyncSession) -> UserModel:
    result = await session.execute(
        select(UserModel).where(
            cast(ColumnElement[bool], UserModel.email == DEMO_EMAIL)
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = UserModel(
            name="AeroField Demo",
            email=DEMO_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            role=UserRole.ADMIN,
        )
        session.add(user)
    else:
        user.name = "AeroField Demo"
        user.password_hash = hash_password(DEMO_PASSWORD)
        user.deleted_at = None
    await session.flush()
    return user


async def _get_or_create_mission(
    session: AsyncSession,
    user_id: int,
) -> MissionModel:
    result = await session.execute(
        select(MissionModel).where(
            cast(ColumnElement[bool], MissionModel.owner_id == user_id),
            cast(ColumnElement[bool], MissionModel.name == DEMO_MISSION_NAME),
        )
    )
    mission = result.scalar_one_or_none()
    if mission is None:
        mission = MissionModel(
            name=DEMO_MISSION_NAME,
            description="Mission demo cho dữ liệu nhiệt độ và độ ẩm.",
            owner_id=user_id,
            status=MissionStatus.IN_PROGRESS,
            started_at=datetime.now(UTC) - timedelta(days=1),
        )
        session.add(mission)
    else:
        mission.status = MissionStatus.IN_PROGRESS
        mission.deleted_at = None
    await session.flush()
    return mission


async def _get_or_create_node(
    session: AsyncSession,
    mission_id: int,
) -> IoTNodeModel:
    result = await session.execute(
        select(IoTNodeModel).where(
            cast(ColumnElement[bool], IoTNodeModel.serial_number == DEMO_NODE_SERIAL)
        )
    )
    node = result.scalar_one_or_none()
    if node is None:
        node = IoTNodeModel(
            name="Cảm biến môi trường ruộng lúa",
            node_type="environment_sensor",
            serial_number=DEMO_NODE_SERIAL,
            mission_id=mission_id,
            latitude=10.8231,
            longitude=106.6297,
        )
        session.add(node)
    else:
        node.mission_id = mission_id
        node.deleted_at = None
    await session.flush()
    return node


async def seed_demo(session: AsyncSession) -> tuple[int, int]:
    """Create or refresh the demo account and its telemetry data."""
    user = await _get_or_create_user(session)
    user_id = cast(int, user.id)
    mission = await _get_or_create_mission(session, user_id)
    mission_id = cast(int, mission.id)
    node = await _get_or_create_node(session, mission_id)
    node_id = cast(int, node.id)

    samples = build_telemetry_samples(node_id)
    session.add_all(cast(list[Any], samples))
    node.last_seen = samples[-1].timestamp
    session.add(node)
    return user_id, len(samples)


async def main() -> None:
    await init_db()
    try:
        async with db_session() as session:
            user_id, sample_count = await seed_demo(session)
    finally:
        await close_db()

    print("Demo data seeded successfully.")
    print(f"User ID: {user_id}")
    print(f"Email: {DEMO_EMAIL}")
    print(f"Password: {DEMO_PASSWORD}")
    print(f"Telemetry samples: {sample_count}")


if __name__ == "__main__":
    asyncio.run(main())
