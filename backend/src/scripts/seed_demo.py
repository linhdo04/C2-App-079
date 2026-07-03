import asyncio
from dataclasses import dataclass
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

DEMO_ADMIN_EMAIL = "admin@aerofield.example.com"
DEMO_ADMIN_PASSWORD = "Admin12345!"
DEMO_OPERATOR_EMAIL = "demo@aerofield.example.com"
DEMO_OPERATOR_PASSWORD = "Demo12345!"
DEMO_MISSION_NAME = "Giám sát ruộng lúa mẫu"
DEMO_NODE_SERIAL = "DEMO-ENV-001"
TELEMETRY_SAMPLE_INTERVAL_MINUTES = 2
TELEMETRY_SAMPLE_COUNT = 24 * 60 // TELEMETRY_SAMPLE_INTERVAL_MINUTES
ANOMALY_SAMPLE_COUNT = 60 // TELEMETRY_SAMPLE_INTERVAL_MINUTES


@dataclass(frozen=True)
class DemoUser:
    name: str
    email: str
    password: str
    role: UserRole


DEMO_USERS = (
    DemoUser(
        name="AeroField Admin",
        email=DEMO_ADMIN_EMAIL,
        password=DEMO_ADMIN_PASSWORD,
        role=UserRole.ADMIN,
    ),
    DemoUser(
        name="AeroField Operator",
        email=DEMO_OPERATOR_EMAIL,
        password=DEMO_OPERATOR_PASSWORD,
        role=UserRole.OPERATOR,
    ),
)


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


async def _get_or_create_user(
    session: AsyncSession,
    demo_user: DemoUser,
) -> UserModel:
    result = await session.execute(
        select(UserModel).where(
            cast(ColumnElement[bool], UserModel.email == demo_user.email)
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = UserModel(
            name=demo_user.name,
            email=demo_user.email,
            password_hash=hash_password(demo_user.password),
            role=demo_user.role,
        )
        session.add(user)
    else:
        user.name = demo_user.name
        user.password_hash = hash_password(demo_user.password)
        user.role = demo_user.role
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


async def seed_demo(session: AsyncSession) -> tuple[int, int, int]:
    """Create or refresh demo users and telemetry owned by the operator."""
    admin = await _get_or_create_user(session, DEMO_USERS[0])
    operator = await _get_or_create_user(session, DEMO_USERS[1])
    admin_id = cast(int, admin.id)
    operator_id = cast(int, operator.id)
    mission = await _get_or_create_mission(session, operator_id)
    mission_id = cast(int, mission.id)
    node = await _get_or_create_node(session, mission_id)
    node_id = cast(int, node.id)

    samples = build_telemetry_samples(node_id)
    session.add_all(cast(list[Any], samples))
    node.last_seen = samples[-1].timestamp
    session.add(node)
    return admin_id, operator_id, len(samples)


async def main() -> None:
    await init_db()
    try:
        async with db_session() as session:
            admin_id, operator_id, sample_count = await seed_demo(session)
    finally:
        await close_db()

    print("Demo data seeded successfully.")
    print(f"Admin ID: {admin_id}")
    print(f"Admin email: {DEMO_ADMIN_EMAIL}")
    print(f"Admin password: {DEMO_ADMIN_PASSWORD}")
    print(f"Operator ID: {operator_id}")
    print(f"Operator email: {DEMO_OPERATOR_EMAIL}")
    print(f"Operator password: {DEMO_OPERATOR_PASSWORD}")
    print(f"Telemetry samples: {sample_count}")


if __name__ == "__main__":
    asyncio.run(main())
