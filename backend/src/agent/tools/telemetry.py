"""Authenticated telemetry production tool."""

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import ColumnElement, func, or_, select

from infrastructure.database.postgres import db_session
from models.base import get_utc_now
from models.iot_node import IoTNodeModel
from models.mission import MissionModel
from models.telemetry import TelemetryModel

from ..react import Tool, ToolContext

LOCAL_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
RelativeTelemetryRange = Literal[
    "last_7_days",
    "last_30_days",
    "previous_week",
    "previous_month",
    "current_week",
    "current_month",
    "today",
    "yesterday",
]


class TelemetryInput(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    relative_range: RelativeTelemetryRange | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "TelemetryInput":
        if (
            self.start_time is not None
            and self.end_time is not None
            and _to_utc(self.start_time) >= _to_utc(self.end_time)
        ):
            raise ValueError("start_time must be before end_time")
        return self


@dataclass(frozen=True)
class TelemetryTimeRange:
    start: datetime
    end: datetime
    label: str


@dataclass(frozen=True)
class TelemetryAggregate:
    count: int
    temperature_avg: float | None
    temperature_min: float | None
    temperature_max: float | None
    humidity_avg: float | None
    humidity_min: float | None
    humidity_max: float | None


class TelemetryTool(Tool):
    name = "telemetry"
    description = (
        "Read temperature and humidity owned by the user. Supports recent samples, "
        "relative_range, start_time, and end_time filters."
    )
    input_model = TelemetryInput
    retryable = True

    async def execute(self, tool_input: BaseModel, context: ToolContext) -> str:
        data = TelemetryInput.model_validate(tool_input)
        if context.user_id is None:
            return "Không thể truy vấn telemetry khi thiếu thông tin người dùng."
        time_range = _resolve_time_range(data, context.goal)
        statement = _latest_telemetry_statement(context.user_id, time_range)
        if time_range is None:
            statement = statement.limit(data.limit)
        async with db_session() as session:
            if time_range is not None:
                aggregate = _parse_aggregate_row(
                    (
                        await session.execute(
                            _aggregate_telemetry_statement(context.user_id, time_range)
                        )
                    ).one()
                )
                rows = (await session.execute(statement.limit(1))).all()
            else:
                aggregate = None
                rows = (await session.execute(statement)).all()
        if not rows:
            if time_range is not None:
                return (
                    "Không có dữ liệu nhiệt độ hoặc độ ẩm cho người dùng trong "
                    f"{time_range.label}."
                )
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
        heading = (
            f"Phân tích {aggregate.count if aggregate is not None else len(rows)} "
            f"mẫu telemetry trong {time_range.label}:"
            if time_range is not None
            else f"Phân tích {len(rows)} mẫu telemetry mới nhất:"
        )
        return "\n".join(
            [
                heading,
                f"- Mission gần nhất: {mission}",
                f"- Thiết bị gần nhất: {node}",
                f"- Thời điểm mẫu mới nhất: {latest.timestamp.isoformat()}",
                (
                    _aggregate_summary(
                        "Nhiệt độ",
                        "°C",
                        (
                            float(latest.temperature_celsius)
                            if latest.temperature_celsius is not None
                            else None
                        ),
                        aggregate.temperature_avg,
                        aggregate.temperature_min,
                        aggregate.temperature_max,
                    )
                    if aggregate is not None
                    else _summary("Nhiệt độ", "°C", temperatures)
                ),
                (
                    _aggregate_summary(
                        "Độ ẩm",
                        "%",
                        (
                            float(latest.humidity_percent)
                            if latest.humidity_percent is not None
                            else None
                        ),
                        aggregate.humidity_avg,
                        aggregate.humidity_min,
                        aggregate.humidity_max,
                    )
                    if aggregate is not None
                    else _summary("Độ ẩm", "%", humidities)
                ),
                "- Đây là số đo lịch sử, không phải dự báo thời tiết.",
            ]
        )


def _latest_telemetry_statement(
    user_id: int, time_range: TelemetryTimeRange | None
) -> Any:
    statement = (
        select(
            TelemetryModel,
            cast(Any, IoTNodeModel.name),
            cast(Any, MissionModel.name),
        )
        .join(IoTNodeModel, cast(Any, TelemetryModel.iot_node_id == IoTNodeModel.id))
        .join(MissionModel, cast(Any, IoTNodeModel.mission_id == MissionModel.id))
        .where(*_telemetry_filters(user_id, time_range))
        .order_by(cast(Any, TelemetryModel.timestamp).desc())
    )
    return statement


def _aggregate_telemetry_statement(user_id: int, time_range: TelemetryTimeRange) -> Any:
    statement = (
        select(
            func.count(cast(Any, TelemetryModel.id)),
            func.avg(cast(Any, TelemetryModel.temperature_celsius)),
            func.min(cast(Any, TelemetryModel.temperature_celsius)),
            func.max(cast(Any, TelemetryModel.temperature_celsius)),
            func.avg(cast(Any, TelemetryModel.humidity_percent)),
            func.min(cast(Any, TelemetryModel.humidity_percent)),
            func.max(cast(Any, TelemetryModel.humidity_percent)),
        )
        .join(IoTNodeModel, cast(Any, TelemetryModel.iot_node_id == IoTNodeModel.id))
        .join(MissionModel, cast(Any, IoTNodeModel.mission_id == MissionModel.id))
        .where(*_telemetry_filters(user_id, time_range))
    )
    return statement


def _telemetry_filters(
    user_id: int,
    time_range: TelemetryTimeRange | None,
) -> list[ColumnElement[bool]]:
    filters = [
        cast(ColumnElement[bool], MissionModel.owner_id == user_id),
        cast(ColumnElement[bool], cast(Any, MissionModel.deleted_at).is_(None)),
        cast(ColumnElement[bool], cast(Any, IoTNodeModel.deleted_at).is_(None)),
        cast(ColumnElement[bool], cast(Any, TelemetryModel.deleted_at).is_(None)),
        or_(
            cast(Any, TelemetryModel.temperature_celsius).is_not(None),
            cast(Any, TelemetryModel.humidity_percent).is_not(None),
        ),
    ]
    if time_range is not None:
        filters.extend(
            [
                cast(
                    ColumnElement[bool],
                    cast(Any, TelemetryModel.timestamp) >= time_range.start,
                ),
                cast(
                    ColumnElement[bool],
                    cast(Any, TelemetryModel.timestamp) < time_range.end,
                ),
            ]
        )
    return filters


def _parse_aggregate_row(row: Any) -> TelemetryAggregate:
    return TelemetryAggregate(
        count=int(row[0] or 0),
        temperature_avg=_optional_float(row[1]),
        temperature_min=_optional_float(row[2]),
        temperature_max=_optional_float(row[3]),
        humidity_avg=_optional_float(row[4]),
        humidity_min=_optional_float(row[5]),
        humidity_max=_optional_float(row[6]),
    )


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _resolve_time_range(
    data: TelemetryInput,
    goal: str,
    *,
    now: datetime | None = None,
) -> TelemetryTimeRange | None:
    if data.start_time is not None or data.end_time is not None:
        if data.end_time is None:
            end = _to_utc(now or get_utc_now())
        else:
            end = _to_utc(data.end_time)
        if data.start_time is None:
            start = end - timedelta(days=30)
        else:
            start = _to_utc(data.start_time)
        return TelemetryTimeRange(
            start=start,
            end=end,
            label=_range_label(start, end),
        )

    if data.relative_range is not None:
        return _relative_range(data.relative_range, now=now)

    parsed_explicit = _parse_explicit_date_range(goal)
    if parsed_explicit is not None:
        return parsed_explicit

    parsed_rolling_count = _parse_rolling_count_range(goal, now=now)
    if parsed_rolling_count is not None:
        return parsed_rolling_count

    parsed_relative = _parse_relative_range(goal)
    if parsed_relative is not None:
        return _relative_range(parsed_relative, now=now)

    return None


def _relative_range(
    relative_range: RelativeTelemetryRange,
    *,
    now: datetime | None = None,
) -> TelemetryTimeRange:
    current = _to_utc(now or get_utc_now()).astimezone(LOCAL_TIMEZONE)
    if relative_range == "last_7_days":
        start = current - timedelta(days=7)
        end = current
        label = "7 ngày qua"
    elif relative_range == "last_30_days":
        start = current - timedelta(days=30)
        end = current
        label = "30 ngày qua"
    elif relative_range == "previous_week":
        end = datetime.combine(
            current.date() - timedelta(days=current.weekday()),
            time.min,
            tzinfo=LOCAL_TIMEZONE,
        )
        start = end - timedelta(days=7)
        label = "tuần trước"
    elif relative_range == "previous_month":
        first_day_current_month = current.date().replace(day=1)
        end = datetime.combine(
            first_day_current_month,
            time.min,
            tzinfo=LOCAL_TIMEZONE,
        )
        previous_month_last_day = first_day_current_month - timedelta(days=1)
        start = datetime.combine(
            previous_month_last_day.replace(day=1),
            time.min,
            tzinfo=LOCAL_TIMEZONE,
        )
        label = "tháng trước"
    elif relative_range == "current_week":
        start = datetime.combine(
            current.date() - timedelta(days=current.weekday()),
            time.min,
            tzinfo=LOCAL_TIMEZONE,
        )
        end = current
        label = "tuần này"
    elif relative_range == "current_month":
        start = datetime.combine(
            current.date().replace(day=1),
            time.min,
            tzinfo=LOCAL_TIMEZONE,
        )
        end = current
        label = "tháng này"
    elif relative_range == "today":
        start = datetime.combine(current.date(), time.min, tzinfo=LOCAL_TIMEZONE)
        end = current
        label = "hôm nay"
    else:
        end_day = current.date()
        start = datetime.combine(
            end_day - timedelta(days=1),
            time.min,
            tzinfo=LOCAL_TIMEZONE,
        )
        end = datetime.combine(end_day, time.min, tzinfo=LOCAL_TIMEZONE)
        label = "hôm qua"
    return TelemetryTimeRange(
        start=start.astimezone(UTC),
        end=end.astimezone(UTC),
        label=label,
    )


def _parse_relative_range(goal: str) -> RelativeTelemetryRange | None:
    normalized = " ".join(goal.casefold().split())
    if "hôm qua" in normalized:
        return "yesterday"
    if "hôm nay" in normalized:
        return "today"
    if "tuần này" in normalized:
        return "current_week"
    if "tháng này" in normalized:
        return "current_month"
    if "tuần trước" in normalized:
        return "previous_week"
    if "tháng trước" in normalized:
        return "previous_month"
    if re.search(r"(?:1\s*)?tuần\s+(?:qua|gần đây|vừa qua)", normalized):
        return "last_7_days"
    if re.search(r"7\s*ngày\s+(?:qua|gần đây|vừa qua)", normalized):
        return "last_7_days"
    if re.search(r"(?:1\s*)?tháng\s+(?:qua|gần đây|vừa qua)", normalized):
        return "last_30_days"
    if re.search(r"30\s*ngày\s+(?:qua|gần đây|vừa qua)", normalized):
        return "last_30_days"
    return None


def _parse_rolling_count_range(
    goal: str,
    *,
    now: datetime | None = None,
) -> TelemetryTimeRange | None:
    normalized = " ".join(goal.casefold().split())
    match = re.search(
        r"\b(?P<count>\d{1,4})\s*(?P<unit>ngày|tuần|tháng)\s*"
        r"(?:qua|gần đây|vừa qua)\b",
        normalized,
    )
    if match is None:
        return None
    count = int(match.group("count"))
    if count <= 0:
        return None
    unit = match.group("unit")
    current = _to_utc(now or get_utc_now()).astimezone(LOCAL_TIMEZONE)
    if unit == "ngày":
        start = current - timedelta(days=count)
    elif unit == "tuần":
        start = current - timedelta(weeks=count)
    else:
        start = _shift_months(current, -count)
    return TelemetryTimeRange(
        start=start.astimezone(UTC),
        end=current.astimezone(UTC),
        label=f"{count} {unit} qua",
    )


def _parse_explicit_date_range(goal: str) -> TelemetryTimeRange | None:
    matches = [_parse_date_match(match) for match in _date_pattern().finditer(goal)]
    dates = [item for item in matches if item is not None]
    if len(dates) < 2:
        return None
    start_date, end_date = dates[0], dates[1]
    if start_date > end_date:
        return None
    start = datetime.combine(start_date, time.min, tzinfo=LOCAL_TIMEZONE)
    end = datetime.combine(
        end_date + timedelta(days=1),
        time.min,
        tzinfo=LOCAL_TIMEZONE,
    )
    return TelemetryTimeRange(
        start=start.astimezone(UTC),
        end=end.astimezone(UTC),
        label=f"từ {start_date.isoformat()} đến {end_date.isoformat()}",
    )


def _date_pattern() -> re.Pattern[str]:
    return re.compile(
        r"\b(?:(?P<ymd>\d{4}-\d{1,2}-\d{1,2})|"
        r"(?P<dmy>\d{1,2}[/-]\d{1,2}[/-]\d{4})|"
        r"(?:(?:ngày\s*)?(?P<vnday>\d{1,2})\s*tháng\s*"
        r"(?P<vnmonth>\d{1,2})\s*năm\s*(?P<vnyear>\d{4})))\b"
    )


def _parse_date_match(match: re.Match[str]) -> date | None:
    if match.group("ymd"):
        try:
            return date.fromisoformat(match.group("ymd"))
        except ValueError:
            return None
    if match.group("vnday"):
        try:
            return date(
                int(match.group("vnyear")),
                int(match.group("vnmonth")),
                int(match.group("vnday")),
            )
        except ValueError:
            return None
    try:
        day, month, year = re.split(r"[/-]", match.group("dmy"))
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _shift_months(value: datetime, months: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + months
    if month_index < 0:
        return value.replace(year=1, month=1, day=1)
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=LOCAL_TIMEZONE)
    return value.astimezone(UTC)


def _range_label(start: datetime, end: datetime) -> str:
    return f"từ {_to_utc(start).isoformat()} đến trước {_to_utc(end).isoformat()}"


def _summary(label: str, unit: str, values: list[float]) -> str:
    if not values:
        return f"- {label}: không có dữ liệu"
    return (
        f"- {label}: mới nhất {values[0]:.1f}{unit}; "
        f"trung bình {sum(values) / len(values):.1f}{unit}; "
        f"thấp nhất {min(values):.1f}{unit}; cao nhất {max(values):.1f}{unit}"
    )


def _aggregate_summary(
    label: str,
    unit: str,
    latest: float | None,
    average: float | None,
    minimum: float | None,
    maximum: float | None,
) -> str:
    if average is None or minimum is None or maximum is None:
        return f"- {label}: không có dữ liệu"
    latest_text = (
        f"mới nhất {latest:.1f}{unit}; "
        if latest is not None
        else "mới nhất không có dữ liệu; "
    )
    return (
        f"- {label}: {latest_text}"
        f"trung bình {average:.1f}{unit}; "
        f"thấp nhất {minimum:.1f}{unit}; cao nhất {maximum:.1f}{unit}"
    )


__all__ = [
    "TelemetryInput",
    "TelemetryTimeRange",
    "TelemetryTool",
]
