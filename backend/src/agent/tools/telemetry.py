"""Authenticated telemetry production tool."""

from typing import Any, cast

from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, or_, select

from infrastructure.database.postgres import db_session
from models.iot_node import IoTNodeModel
from models.mission import MissionModel
from models.telemetry import TelemetryModel

from ..react import Tool, ToolContext


class TelemetryInput(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)


class TelemetryTool(Tool):
    name = "telemetry"
    description = "Read recent temperature and humidity owned by the user."
    input_model = TelemetryInput
    retryable = True

    async def execute(self, tool_input: BaseModel, context: ToolContext) -> str:
        data = TelemetryInput.model_validate(tool_input)
        if context.user_id is None:
            return "Không thể truy vấn telemetry khi thiếu thông tin người dùng."
        statement = (
            select(
                TelemetryModel,
                cast(Any, IoTNodeModel.name),
                cast(Any, MissionModel.name),
            )
            .join(
                IoTNodeModel, cast(Any, TelemetryModel.iot_node_id == IoTNodeModel.id)
            )
            .join(MissionModel, cast(Any, IoTNodeModel.mission_id == MissionModel.id))
            .where(
                cast(ColumnElement[bool], MissionModel.owner_id == context.user_id),
                cast(ColumnElement[bool], cast(Any, MissionModel.deleted_at).is_(None)),
                cast(ColumnElement[bool], cast(Any, IoTNodeModel.deleted_at).is_(None)),
                cast(
                    ColumnElement[bool], cast(Any, TelemetryModel.deleted_at).is_(None)
                ),
                or_(
                    cast(Any, TelemetryModel.temperature_celsius).is_not(None),
                    cast(Any, TelemetryModel.humidity_percent).is_not(None),
                ),
            )
            .order_by(cast(Any, TelemetryModel.timestamp).desc())
            .limit(data.limit)
        )
        async with db_session() as session:
            rows = (await session.execute(statement)).all()
        if not rows:
            return "Không có dữ liệu nhiệt độ hoặc độ ẩm cho người dùng."
        temperatures = [
            float(row.temperature_celsius)
            for row, _, _ in rows
            if row.temperature_celsius is not None
        ]
        humidities = [
            float(row.humidity_percent)
            for row, _, _ in rows
            if row.humidity_percent is not None
        ]
        latest, node, mission = rows[0]
        return "\n".join(
            [
                f"Phân tích {len(rows)} mẫu telemetry mới nhất:",
                f"- Mission gần nhất: {mission}",
                f"- Thiết bị gần nhất: {node}",
                f"- Thời điểm mẫu mới nhất: {latest.timestamp.isoformat()}",
                _summary("Nhiệt độ", "°C", temperatures),
                _summary("Độ ẩm", "%", humidities),
                "- Đây là số đo lịch sử, không phải dự báo thời tiết.",
            ]
        )


def _summary(label: str, unit: str, values: list[float]) -> str:
    if not values:
        return f"- {label}: không có dữ liệu"
    return (
        f"- {label}: mới nhất {values[0]:.1f}{unit}; "
        f"trung bình {sum(values) / len(values):.1f}{unit}; "
        f"thấp nhất {min(values):.1f}{unit}; cao nhất {max(values):.1f}{unit}"
    )


__all__ = ["TelemetryInput", "TelemetryTool"]
