from typing import Any, cast

from langchain_core.tools import tool
from sqlalchemy import ColumnElement, or_, select

from infrastructure.database.postgres import db_session
from models.iot_node import IoTNodeModel
from models.mission import MissionModel
from models.telemetry import TelemetryModel


def _metric_summary(label: str, unit: str, values: list[float]) -> str:
    if not values:
        return f"- {label}: không có dữ liệu"
    average = sum(values) / len(values)
    return (
        f"- {label}: mới nhất {values[0]:.1f}{unit}; "
        f"trung bình {average:.1f}{unit}; "
        f"thấp nhất {min(values):.1f}{unit}; cao nhất {max(values):.1f}{unit}"
    )


@tool
async def analyze_environment_telemetry(user_id: int, limit: int = 50) -> str:
    """Phân tích các mẫu nhiệt độ và độ ẩm mới nhất thuộc mission của user."""
    sample_limit = max(1, min(limit, 100))
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
            cast(ColumnElement[bool], MissionModel.owner_id == user_id),
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
        .limit(sample_limit)
    )

    async with db_session() as session:
        result = await session.execute(statement)
        rows = result.all()

    if not rows:
        return "Không có dữ liệu nhiệt độ hoặc độ ẩm cho các mission của người dùng."

    temperatures = [
        float(telemetry.temperature_celsius)
        for telemetry, _node_name, _mission_name in rows
        if telemetry.temperature_celsius is not None
    ]
    humidities = [
        float(telemetry.humidity_percent)
        for telemetry, _node_name, _mission_name in rows
        if telemetry.humidity_percent is not None
    ]
    latest, latest_node, latest_mission = rows[0]

    return "\n".join(
        [
            f"Phân tích {len(rows)} mẫu telemetry mới nhất:",
            f"- Mission gần nhất: {latest_mission}",
            f"- Thiết bị gần nhất: {latest_node}",
            f"- Thời điểm mẫu mới nhất: {latest.timestamp.isoformat()}",
            _metric_summary("Nhiệt độ", "°C", temperatures),
            _metric_summary("Độ ẩm", "%", humidities),
            ("Dữ liệu trên là số đo lịch sử từ database, không phải dự báo thời tiết."),
        ]
    )
