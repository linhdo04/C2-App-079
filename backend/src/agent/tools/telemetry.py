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
POINT_LOOKUP_TOLERANCE = timedelta(minutes=5)
TelemetryQueryKind = Literal[
    "temperature_max",
    "temperature_min",
    "temperature_at",
    "humidity_max",
    "humidity_min",
    "humidity_at",
]
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
TelemetryTemporalIntentKind = Literal["rolling"]
TelemetryTemporalUnit = Literal["minute", "hour", "day", "week", "month"]


class TelemetryTemporalIntent(BaseModel):
    kind: TelemetryTemporalIntentKind = Field(
        description="Temporal intent type. Use rolling for N units ago/from now."
    )
    count: int = Field(ge=1, le=1000, description="Number of time units.")
    unit: TelemetryTemporalUnit = Field(
        description="Rolling range unit: minute, hour, day, week, or month."
    )


class TelemetryInput(BaseModel):
    limit: int = Field(default=50, ge=1, le=100)
    query_kinds: list[TelemetryQueryKind] | None = Field(
        default=None,
        min_length=1,
        max_length=4,
        description=(
            "Specific telemetry facts to query. Use temperature_max/min or "
            "humidity_max/min when the user asks for highest/lowest values. "
            "Use temperature_at or humidity_at when the user asks for the value "
            "at a specific time."
        ),
    )
    relative_range: RelativeTelemetryRange | None = None
    temporal_intent: TelemetryTemporalIntent | None = Field(
        default=None,
        description=(
            "Structured temporal intent extracted from the user's request. Use for "
            "arbitrary rolling ranges like last 2 hours or last 30 minutes."
        ),
    )
    start_time: datetime | None = None
    end_time: datetime | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "TelemetryInput":
        if (
            self.start_time is not None
            and self.end_time is not None
            and _to_utc(self.start_time) >= _to_utc(self.end_time)
            and not _has_point_query(self.query_kinds)
        ):
            raise ValueError("start_time must be before end_time")
        if self.query_kinds is not None:
            self.query_kinds = list(dict.fromkeys(self.query_kinds))
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
        "relative_range, temporal_intent, start_time, and end_time filters."
    )
    input_model = TelemetryInput
    retryable = True

    async def execute(self, tool_input: BaseModel, context: ToolContext) -> str:
        data = TelemetryInput.model_validate(tool_input)
        if context.user_id is None:
            return "Không thể truy vấn telemetry khi thiếu thông tin người dùng."
        time_range = _resolve_time_range(data, context.goal)
        if (
            data.query_kinds is not None
            and time_range is None
            and any(not _is_point_query(query_kind) for query_kind in data.query_kinds)
        ):
            time_range = _relative_range("today")
        if data.query_kinds is not None:
            return await _execute_specific_queries(
                data,
                context.user_id,
                time_range,
                context.goal,
            )
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
                f"- Thời điểm mẫu mới nhất: {_format_local_datetime(latest.timestamp)}",
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


async def _execute_specific_queries(
    data: TelemetryInput,
    user_id: int,
    time_range: TelemetryTimeRange | None,
    goal: str,
) -> str:
    assert data.query_kinds is not None
    point_time = _resolve_point_lookup_time(goal)
    if point_time is None and data.start_time is not None:
        point_time = _to_utc(data.start_time)
    lines = [
        (
            f"Truy vấn telemetry tại thời điểm {_format_local_datetime(point_time)}:"
            if point_time is not None
            else f"Truy vấn telemetry theo chỉ số trong {time_range.label}:"
            if time_range is not None
            else f"Truy vấn telemetry theo chỉ số trong {data.limit} mẫu mới nhất:"
        )
    ]
    async with db_session() as session:
        for query_kind in data.query_kinds:
            if _is_point_query(query_kind):
                if point_time is None:
                    lines.append(_missing_point_time_summary(query_kind))
                    continue
                statement = _point_telemetry_statement(user_id, point_time, query_kind)
                rows = list((await session.execute(statement.limit(1))).all())
                lines.append(_point_query_summary(query_kind, rows, point_time))
                continue

            statement = _specific_telemetry_statement(user_id, time_range, query_kind)
            if time_range is None:
                statement = statement.limit(data.limit)
            rows = list((await session.execute(statement.limit(1))).all())
            lines.append(_specific_query_summary(query_kind, rows, time_range))
    lines.append("- Đây là số đo lịch sử, không phải dự báo thời tiết.")
    return "\n".join(lines)


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


def _specific_telemetry_statement(
    user_id: int,
    time_range: TelemetryTimeRange | None,
    query_kind: TelemetryQueryKind,
) -> Any:
    field = _query_field(query_kind)
    order_by_value = (
        cast(Any, field).asc()
        if query_kind.endswith("_min")
        else cast(Any, field).desc()
    )
    statement = (
        select(
            TelemetryModel,
            cast(Any, IoTNodeModel.name),
            cast(Any, MissionModel.name),
        )
        .join(IoTNodeModel, cast(Any, TelemetryModel.iot_node_id == IoTNodeModel.id))
        .join(MissionModel, cast(Any, IoTNodeModel.mission_id == MissionModel.id))
        .where(
            *_telemetry_filters(user_id, time_range),
            cast(ColumnElement[bool], cast(Any, field).is_not(None)),
        )
        .order_by(
            order_by_value,
            cast(Any, TelemetryModel.timestamp).desc(),
            cast(Any, TelemetryModel.id).desc(),
        )
    )
    return statement


def _point_telemetry_statement(
    user_id: int,
    point_time: datetime,
    query_kind: TelemetryQueryKind,
) -> Any:
    field = _query_field(query_kind)
    start = point_time - POINT_LOOKUP_TOLERANCE
    end = point_time + POINT_LOOKUP_TOLERANCE
    distance_seconds = func.abs(
        func.extract("epoch", cast(Any, TelemetryModel.timestamp) - point_time)
    )
    statement = (
        select(
            TelemetryModel,
            cast(Any, IoTNodeModel.name),
            cast(Any, MissionModel.name),
        )
        .join(IoTNodeModel, cast(Any, TelemetryModel.iot_node_id == IoTNodeModel.id))
        .join(MissionModel, cast(Any, IoTNodeModel.mission_id == MissionModel.id))
        .where(
            *_telemetry_filters(user_id, None),
            cast(ColumnElement[bool], cast(Any, field).is_not(None)),
            cast(
                ColumnElement[bool],
                cast(Any, TelemetryModel.timestamp) >= start,
            ),
            cast(
                ColumnElement[bool],
                cast(Any, TelemetryModel.timestamp) <= end,
            ),
        )
        .order_by(
            distance_seconds.asc(),
            cast(Any, TelemetryModel.timestamp).desc(),
            cast(Any, TelemetryModel.id).desc(),
        )
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


def _query_field(query_kind: TelemetryQueryKind) -> Any:
    if query_kind.startswith("temperature"):
        return TelemetryModel.temperature_celsius
    return TelemetryModel.humidity_percent


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

    if data.temporal_intent is not None:
        return _temporal_intent_range(data.temporal_intent, now=now)

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


def _temporal_intent_range(
    temporal_intent: TelemetryTemporalIntent,
    *,
    now: datetime | None = None,
) -> TelemetryTimeRange:
    current = _to_utc(now or get_utc_now()).astimezone(LOCAL_TIMEZONE)
    count = temporal_intent.count
    unit = temporal_intent.unit
    if unit == "minute":
        start = current - timedelta(minutes=count)
        label_unit = "phút"
    elif unit == "hour":
        start = current - timedelta(hours=count)
        label_unit = "giờ"
    elif unit == "day":
        start = current - timedelta(days=count)
        label_unit = "ngày"
    elif unit == "week":
        start = current - timedelta(weeks=count)
        label_unit = "tuần"
    else:
        start = _shift_months(current, -count)
        label_unit = "tháng"
    return TelemetryTimeRange(
        start=start.astimezone(UTC),
        end=current.astimezone(UTC),
        label=f"{count} {label_unit} qua",
    )


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
        r"\b(?P<count>\d{1,4}|một|hai|ba|bốn|bon|năm|nam|sáu|sau|bảy|bay|"
        r"tám|tam|chín|chin|mười|muoi)\s*"
        r"(?P<unit>phút|giờ|tiếng|ngày|tuần|tháng)\s*"
        r"(?:qua|gần đây|vừa qua|vừa rồi)\b",
        normalized,
    )
    if match is None:
        return None
    count = _parse_vietnamese_count(match.group("count"))
    if count <= 0:
        return None
    unit = match.group("unit")
    current = _to_utc(now or get_utc_now()).astimezone(LOCAL_TIMEZONE)
    if unit == "phút":
        start = current - timedelta(minutes=count)
        label_unit = "phút"
    elif unit in {"giờ", "tiếng"}:
        start = current - timedelta(hours=count)
        label_unit = "giờ"
    elif unit == "ngày":
        start = current - timedelta(days=count)
        label_unit = "ngày"
    elif unit == "tuần":
        start = current - timedelta(weeks=count)
        label_unit = "tuần"
    else:
        start = _shift_months(current, -count)
        label_unit = "tháng"
    return TelemetryTimeRange(
        start=start.astimezone(UTC),
        end=current.astimezone(UTC),
        label=f"{count} {label_unit} qua",
    )


def _parse_vietnamese_count(value: str) -> int:
    if value.isdigit():
        return int(value)
    counts = {
        "một": 1,
        "hai": 2,
        "ba": 3,
        "bốn": 4,
        "bon": 4,
        "năm": 5,
        "nam": 5,
        "sáu": 6,
        "sau": 6,
        "bảy": 7,
        "bay": 7,
        "tám": 8,
        "tam": 8,
        "chín": 9,
        "chin": 9,
        "mười": 10,
        "muoi": 10,
    }
    return counts.get(value, 0)


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


def _resolve_point_lookup_time(
    goal: str,
    *,
    now: datetime | None = None,
) -> datetime | None:
    match = _point_time_pattern().search(goal)
    if match is None:
        return None

    current = _to_utc(now or get_utc_now()).astimezone(LOCAL_TIMEZONE)
    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    requested_date = _parse_point_date(goal, current.date())
    if requested_date is None:
        return None
    local_requested = datetime.combine(
        requested_date,
        time(hour=hour, minute=minute),
        tzinfo=LOCAL_TIMEZONE,
    )
    return local_requested.astimezone(UTC)


def _point_time_pattern() -> re.Pattern[str]:
    return re.compile(
        r"\b(?P<hour>[01]?\d|2[0-3])\s*(?::|h|giờ)\s*(?P<minute>[0-5]\d)?\b",
        re.IGNORECASE,
    )


def _parse_point_date(goal: str, current_date: date) -> date | None:
    ymd_match = re.search(
        r"\b(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})\b",
        goal,
    )
    if ymd_match is not None:
        return _safe_date(
            int(ymd_match.group("year")),
            int(ymd_match.group("month")),
            int(ymd_match.group("day")),
        )

    dmy_match = re.search(
        r"\b(?P<day>[1-9]|[12]\d|3[01])\s*(?:/|-|\.)\s*"
        r"(?P<month>[1-9]|1[0-2])"
        r"(?:\s*(?:/|-|\.)\s*(?P<year>\d{2,4}))?\b",
        goal,
    )
    if dmy_match is not None:
        return _safe_date(
            _coerce_year(dmy_match.group("year"), current_date.year),
            int(dmy_match.group("month")),
            int(dmy_match.group("day")),
        )

    vn_match = re.search(
        r"\bngày\s*(?P<day>[1-9]|[12]\d|3[01])"
        r"(?:\s*tháng\s*(?P<month>[1-9]|1[0-2]))?"
        r"(?:\s*năm\s*(?P<year>\d{2,4}))?\b",
        goal,
        re.IGNORECASE,
    )
    if vn_match is not None:
        return _safe_date(
            _coerce_year(vn_match.group("year"), current_date.year),
            int(vn_match.group("month") or current_date.month),
            int(vn_match.group("day")),
        )

    return current_date


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _coerce_year(value: str | None, default: int) -> int:
    if value is None:
        return default
    year = int(value)
    if year < 100:
        return 2000 + year
    return year


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
    return f"từ {_format_local_datetime(start)} đến trước {_format_local_datetime(end)}"


def _format_local_datetime(value: datetime) -> str:
    local_value = _to_utc(value).astimezone(LOCAL_TIMEZONE)
    return f"{local_value:%H:%M:%S ngày %d/%m/%Y} (giờ Việt Nam)"


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


def _specific_query_summary(
    query_kind: TelemetryQueryKind,
    rows: list[Any],
    time_range: TelemetryTimeRange | None,
) -> str:
    label, unit, stat_label = _query_display(query_kind)
    range_text = _query_range_text(time_range)
    if not rows:
        return f"- Không có dữ liệu {label.casefold()}{range_text}."
    telemetry, node, mission = rows[0]
    value = (
        telemetry.temperature_celsius
        if query_kind.startswith("temperature")
        else telemetry.humidity_percent
    )
    return (
        f"- {label} {stat_label}{range_text}: {float(value):.1f}{unit}; "
        f"thời điểm {_format_local_datetime(telemetry.timestamp)}; "
        f"thiết bị {node}; mission {mission}"
    )


def _point_query_summary(
    query_kind: TelemetryQueryKind,
    rows: list[Any],
    point_time: datetime,
) -> str:
    label, unit, _ = _query_display(query_kind)
    requested_text = _format_local_datetime(point_time)
    if not rows:
        return (
            f"- Không có dữ liệu {label.casefold()} trong ±5 phút quanh "
            f"{requested_text}."
        )
    telemetry, node, mission = rows[0]
    value = (
        telemetry.temperature_celsius
        if query_kind.startswith("temperature")
        else telemetry.humidity_percent
    )
    delta_seconds = abs((_to_utc(telemetry.timestamp) - point_time).total_seconds())
    return (
        f"- {label} gần {requested_text}: {float(value):.1f}{unit}; "
        f"mẫu thực tế {_format_local_datetime(telemetry.timestamp)} "
        f"(lệch {_format_duration(delta_seconds)}); "
        f"thiết bị {node}; mission {mission}"
    )


def _missing_point_time_summary(query_kind: TelemetryQueryKind) -> str:
    label, _, _ = _query_display(query_kind)
    return f"- Cần thời điểm cụ thể để truy vấn {label.casefold()} tại thời điểm đó."


def _is_point_query(query_kind: TelemetryQueryKind) -> bool:
    return query_kind.endswith("_at")


def _has_point_query(query_kinds: list[TelemetryQueryKind] | None) -> bool:
    return query_kinds is not None and any(
        _is_point_query(query_kind) for query_kind in query_kinds
    )


def _format_duration(seconds: float) -> str:
    rounded = int(round(seconds))
    minutes, remaining_seconds = divmod(rounded, 60)
    if minutes == 0:
        return f"{remaining_seconds} giây"
    if remaining_seconds == 0:
        return f"{minutes} phút"
    return f"{minutes} phút {remaining_seconds} giây"


def _query_display(query_kind: TelemetryQueryKind) -> tuple[str, str, str]:
    if query_kind == "temperature_max":
        return "Nhiệt độ", "°C", "cao nhất"
    if query_kind == "temperature_min":
        return "Nhiệt độ", "°C", "thấp nhất"
    if query_kind == "humidity_max":
        return "Độ ẩm", "%", "cao nhất"
    if query_kind == "humidity_min":
        return "Độ ẩm", "%", "thấp nhất"
    if query_kind == "temperature_at":
        return "Nhiệt độ", "°C", "tại thời điểm"
    return "Độ ẩm", "%", "tại thời điểm"


def _query_range_text(time_range: TelemetryTimeRange | None) -> str:
    if time_range is None:
        return ""
    if time_range.label.startswith("từ "):
        return f" {time_range.label}"
    return f" trong {time_range.label}"


__all__ = [
    "TelemetryInput",
    "TelemetryTemporalIntent",
    "TelemetryQueryKind",
    "TelemetryTimeRange",
    "TelemetryTool",
]
