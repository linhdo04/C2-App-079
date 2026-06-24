"""Agent facade and production tool tests."""

import asyncio
import os
from collections.abc import Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fakes import FakePolicyLLM

from agent import run_agent, stream_agent
from agent.prompts import SYSTEM_PROMPT
from agent.react import (
    Action,
    AgentLoopResult,
    CallableTool,
    ConversationMessage,
    InMemoryMemory,
    Memory,
    ReActStep,
    ReasoningDecision,
    Tool,
)
from agent.reasoners import (
    FallbackReasoner,
    FallbackRouteDecision,
    LLMReasoner,
    LLMRoutedFallbackReasoner,
    LLMToolRouter,
    _extract_server_retry_delay,
    _llm_error_metadata,
    _parse_fallback_route_decision,
    _parse_reasoning_decision,
    classify_llm_error,
)
from agent.structured import bind_structured_output
from agent.tool_policy import SemanticToolPolicy, _parse_tool_policy_decision
from agent.tools import CalculatorTool, SearchInput, SearchTool, TelemetryInput
from agent.tools.search import (
    FilteredSearchResult,
    RejectedSearchResult,
    SearchFilterDecision,
    SearchFilterInput,
    SearchResultFilter,
    UsableClaim,
    _parse_filter_decision,
)
from agent.tools.telemetry import (
    TelemetryTemporalIntent,
    TelemetryTool,
    _resolve_time_range,
)
from models.telemetry import TelemetryModel


class RateLimitError(Exception):
    status_code = 429


class FakeTelemetryResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows

    def one(self) -> Any:
        return self.rows[0]


class FakeTelemetrySession:
    def __init__(self, responses: list[list[Any]]) -> None:
        self.responses = responses
        self.statements: list[Any] = []
        self.execute_calls = 0

    async def execute(self, statement: Any) -> FakeTelemetryResult:
        self.statements.append(statement)
        response = self.responses[self.execute_calls]
        self.execute_calls += 1
        return FakeTelemetryResult(response)


@pytest.mark.asyncio
async def test_calculator_rejects_unsafe_and_large_expressions() -> None:
    from agent.react import ToolContext
    from agent.tools.calculator import CalculatorInput

    tool = CalculatorTool()
    context = ToolContext(goal="calculate")
    valid = await tool.execute(CalculatorInput(expression="(6 + 4) * 3"), context)
    unsafe = await tool.execute(
        CalculatorInput(expression="__import__('os').system('id')"), context
    )
    huge = await tool.execute(CalculatorInput(expression="10 ** 1000"), context)
    assert valid == "30"
    assert "không hợp lệ" in unsafe
    assert "không hợp lệ" in huge


@pytest.mark.asyncio
async def test_search_tool_includes_result_links() -> None:
    from agent.react import ToolContext

    class FakeClient:
        def search(self, *, query: str, max_results: int) -> dict[str, Any]:
            assert query == "rice price"
            assert max_results == 1
            return {
                "results": [
                    {
                        "title": "Rice market",
                        "content": "Prices increased this week.",
                        "url": "https://example.com/rice-market",
                    }
                ]
            }

    tool = SearchTool.__new__(SearchTool)
    tool._client = FakeClient()

    result = await tool.execute(
        SearchInput(query="rice price", max_results=1),
        ToolContext(goal="search"),
    )

    assert "Rice market" in result
    assert "Prices increased this week." in result
    assert "URL: https://example.com/rice-market" in result


@pytest.mark.asyncio
async def test_search_tool_filters_observation_with_coverage() -> None:
    from agent.react import ToolContext

    class FakeClient:
        def search(self, *, query: str, max_results: int) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "title": "Rice market",
                        "content": "Prices increased this week.",
                        "url": "https://example.com/rice-market",
                    },
                    {
                        "title": "Unrelated",
                        "content": "Movie listings.",
                        "url": "https://example.com/movies",
                    },
                ]
            }

    class FakeFilter:
        async def filter(self, data: Any) -> SearchFilterDecision:
            assert data.question == "rice price"
            assert len(data.results) == 2
            return SearchFilterDecision(
                coverage="partial",
                relevant_results=[
                    FilteredSearchResult(
                        title="Rice market",
                        url="https://example.com/rice-market",
                        summary="Rice prices increased this week.",
                        usable_claims=[
                            UsableClaim(
                                claim="Prices increased this week.",
                                source_url="https://example.com/rice-market",
                            )
                        ],
                        relevance_reason="Directly discusses rice prices.",
                    )
                ],
                rejected_results=[
                    RejectedSearchResult(
                        title="Unrelated",
                        url="https://example.com/movies",
                        reason="Not about rice.",
                    )
                ],
            )

    tool = SearchTool.__new__(SearchTool)
    tool._client = FakeClient()
    setattr(tool, "_result_filter", FakeFilter())

    result = await tool.execute(
        SearchInput(query="rice price", max_results=2),
        ToolContext(goal="search"),
    )

    assert "Coverage: partial" in result
    assert "Rejected results: 1" in result
    assert "Rice market" in result
    assert "Prices increased this week." in result
    assert "https://example.com/rice-market" in result
    assert "Movie listings" not in result
    assert "https://example.com/movies" not in result


@pytest.mark.asyncio
async def test_search_tool_falls_back_to_raw_results_when_filter_fails() -> None:
    from agent.react import ToolContext

    class FakeClient:
        def search(self, *, query: str, max_results: int) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "title": "Rice market",
                        "content": "Prices increased this week.",
                        "url": "https://example.com/rice-market",
                    }
                ]
            }

    class FailingFilter:
        async def filter(self, data: Any) -> SearchFilterDecision:
            raise TimeoutError

    tool = SearchTool.__new__(SearchTool)
    tool._client = FakeClient()
    setattr(tool, "_result_filter", FailingFilter())

    result = await tool.execute(
        SearchInput(query="rice price", max_results=1),
        ToolContext(goal="search"),
    )

    assert "lọc kết quả thất bại" in result
    assert "Rice market" in result
    assert "Snippet: Prices increased this week." in result


@pytest.mark.asyncio
async def test_search_tool_drops_filter_results_with_unknown_urls() -> None:
    from agent.react import ToolContext

    class FakeClient:
        def search(self, *, query: str, max_results: int) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "title": "Rice market",
                        "content": "Prices increased this week.",
                        "url": "https://example.com/rice-market",
                    }
                ]
            }

    class BadUrlFilter:
        async def filter(self, data: Any) -> SearchFilterDecision:
            return SearchFilterDecision(
                coverage="insufficient",
                relevant_results=[
                    FilteredSearchResult(
                        title="Invented",
                        url="https://example.com/invented",
                        summary="Invented summary.",
                        usable_claims=[
                            UsableClaim(
                                claim="Invented claim.",
                                source_url="https://example.com/invented",
                            )
                        ],
                        relevance_reason="Invented reason.",
                    )
                ],
                rejected_results=[],
            )

    tool = SearchTool.__new__(SearchTool)
    tool._client = FakeClient()
    setattr(tool, "_result_filter", BadUrlFilter())

    result = await tool.execute(
        SearchInput(query="rice price", max_results=1),
        ToolContext(goal="search"),
    )

    assert "Coverage: insufficient" in result
    assert "Không tìm thấy nguồn đủ phù hợp" in result
    assert "Invented" not in result
    assert "https://example.com/invented" not in result


def test_telemetry_time_range_resolves_relative_periods() -> None:
    now = datetime(2026, 6, 22, 3, 0, tzinfo=UTC)

    rolling_week = _resolve_time_range(
        TelemetryInput(relative_range="last_7_days"),
        "độ ẩm 1 tuần qua",
        now=now,
    )
    previous_week = _resolve_time_range(
        TelemetryInput(relative_range="previous_week"),
        "độ ẩm tuần trước",
        now=now,
    )
    previous_month = _resolve_time_range(
        TelemetryInput(relative_range="previous_month"),
        "nhiệt độ tháng trước",
        now=now,
    )

    assert rolling_week is not None
    assert rolling_week.start == datetime(2026, 6, 15, 3, 0, tzinfo=UTC)
    assert rolling_week.end == now
    assert rolling_week.label == "7 ngày qua"
    assert previous_week is not None
    assert previous_week.start == datetime(2026, 6, 14, 17, 0, tzinfo=UTC)
    assert previous_week.end == datetime(2026, 6, 21, 17, 0, tzinfo=UTC)
    assert previous_month is not None
    assert previous_month.start == datetime(2026, 4, 30, 17, 0, tzinfo=UTC)
    assert previous_month.end == datetime(2026, 5, 31, 17, 0, tzinfo=UTC)


def test_telemetry_time_range_resolves_arbitrary_rolling_periods() -> None:
    now = datetime(2026, 6, 23, 3, 0, tzinfo=UTC)

    two_weeks = _resolve_time_range(TelemetryInput(), "độ ẩm 2 tuần qua", now=now)
    fourteen_days = _resolve_time_range(
        TelemetryInput(), "nhiệt độ 14 ngày gần đây", now=now
    )
    three_months = _resolve_time_range(
        TelemetryInput(), "telemetry 3 tháng vừa qua", now=now
    )
    two_hours = _resolve_time_range(
        TelemetryInput(), "trong hai tiếng vừa rồi nhiệt độ cao nhất", now=now
    )
    thirty_minutes = _resolve_time_range(
        TelemetryInput(), "độ ẩm 30 phút gần đây", now=now
    )
    temporal_intent_hours = _resolve_time_range(
        TelemetryInput(
            temporal_intent=TelemetryTemporalIntent(
                kind="rolling",
                count=2,
                unit="hour",
            )
        ),
        "trong hai tiếng vừa rồi nhiệt độ cao nhất",
        now=now,
    )

    assert two_weeks is not None
    assert two_weeks.start == datetime(2026, 6, 9, 3, 0, tzinfo=UTC)
    assert two_weeks.end == now
    assert two_weeks.label == "2 tuần qua"
    assert fourteen_days is not None
    assert fourteen_days.start == datetime(2026, 6, 9, 3, 0, tzinfo=UTC)
    assert fourteen_days.label == "14 ngày qua"
    assert three_months is not None
    assert three_months.start == datetime(2026, 3, 23, 3, 0, tzinfo=UTC)
    assert three_months.label == "3 tháng qua"
    assert two_hours is not None
    assert two_hours.start == datetime(2026, 6, 23, 1, 0, tzinfo=UTC)
    assert two_hours.end == now
    assert two_hours.label == "2 giờ qua"
    assert thirty_minutes is not None
    assert thirty_minutes.start == datetime(2026, 6, 23, 2, 30, tzinfo=UTC)
    assert thirty_minutes.end == now
    assert thirty_minutes.label == "30 phút qua"
    assert temporal_intent_hours is not None
    assert temporal_intent_hours.start == datetime(2026, 6, 23, 1, 0, tzinfo=UTC)
    assert temporal_intent_hours.end == now
    assert temporal_intent_hours.label == "2 giờ qua"


def test_telemetry_time_range_resolves_current_week_and_month() -> None:
    now = datetime(2026, 6, 23, 3, 0, tzinfo=UTC)

    current_week = _resolve_time_range(
        TelemetryInput(relative_range="current_week"),
        "telemetry tuần này",
        now=now,
    )
    current_month = _resolve_time_range(
        TelemetryInput(),
        "telemetry tháng này",
        now=now,
    )

    assert current_week is not None
    assert current_week.start == datetime(2026, 6, 21, 17, 0, tzinfo=UTC)
    assert current_week.end == now
    assert current_week.label == "tuần này"
    assert current_month is not None
    assert current_month.start == datetime(2026, 5, 31, 17, 0, tzinfo=UTC)
    assert current_month.end == now
    assert current_month.label == "tháng này"


def test_telemetry_time_range_parses_explicit_date_range() -> None:
    resolved = _resolve_time_range(
        TelemetryInput(),
        "Phân tích telemetry từ 01/06/2026 đến 07/06/2026",
    )

    assert resolved is not None
    assert resolved.start == datetime(2026, 5, 31, 17, 0, tzinfo=UTC)
    assert resolved.end == datetime(2026, 6, 7, 17, 0, tzinfo=UTC)
    assert resolved.label == "từ 2026-06-01 đến 2026-06-07"


def test_telemetry_time_range_parses_vietnamese_long_date_range() -> None:
    resolved = _resolve_time_range(
        TelemetryInput(),
        "Phân tích telemetry từ ngày 1 tháng 6 năm 2026 đến ngày 7 tháng 6 năm 2026",
    )

    assert resolved is not None
    assert resolved.start == datetime(2026, 5, 31, 17, 0, tzinfo=UTC)
    assert resolved.end == datetime(2026, 6, 7, 17, 0, tzinfo=UTC)
    assert resolved.label == "từ 2026-06-01 đến 2026-06-07"


def test_telemetry_time_range_treats_naive_datetimes_as_vietnam_time() -> None:
    resolved = _resolve_time_range(
        TelemetryInput(
            start_time=datetime(2026, 6, 1),
            end_time=datetime(2026, 6, 2),
        ),
        "telemetry",
    )

    assert resolved is not None
    assert resolved.start == datetime(2026, 5, 31, 17, 0, tzinfo=UTC)
    assert resolved.end == datetime(2026, 6, 1, 17, 0, tzinfo=UTC)


def test_telemetry_input_rejects_invalid_explicit_range() -> None:
    with pytest.raises(ValueError):
        TelemetryInput(
            start_time=datetime(2026, 6, 8, tzinfo=UTC),
            end_time=datetime(2026, 6, 7, tzinfo=UTC),
        )


def test_telemetry_input_allows_equal_point_lookup_datetimes() -> None:
    data = TelemetryInput(
        query_kinds=["temperature_at"],
        start_time=datetime(2026, 6, 23, 5, 18, tzinfo=UTC),
        end_time=datetime(2026, 6, 23, 5, 18, tzinfo=UTC),
    )

    assert data.query_kinds == ["temperature_at"]


@pytest.mark.asyncio
async def test_telemetry_tool_filters_and_summarizes_time_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.react import ToolContext

    latest_row = (
        TelemetryModel(
            id=2,
            iot_node_id=1,
            timestamp=datetime(2026, 6, 7, 8, 0, tzinfo=UTC),
            temperature_celsius=32,
            humidity_percent=70,
        ),
        "Cảm biến 01",
        "Ruộng lúa",
    )
    session = FakeTelemetrySession(
        [
            [(2, 30, 28, 32, 75, 70, 80)],
            [latest_row],
        ]
    )

    @asynccontextmanager
    async def fake_db_session() -> Any:
        yield session

    monkeypatch.setattr("agent.tools.telemetry.db_session", fake_db_session)

    result = await TelemetryTool().execute(
        TelemetryInput(
            start_time=datetime(2026, 6, 1, tzinfo=UTC),
            end_time=datetime(2026, 6, 8, tzinfo=UTC),
        ),
        ToolContext(goal="telemetry tuần đầu tháng 6", user_id=7),
    )

    aggregate_statement, latest_statement = session.statements
    statement_text = str(aggregate_statement)
    params = aggregate_statement.compile().params
    assert "telemetry.timestamp >= " in statement_text
    assert "telemetry.timestamp < " in statement_text
    assert aggregate_statement._limit_clause is None
    assert latest_statement._limit_clause.value == 1
    assert datetime(2026, 6, 1, tzinfo=UTC) in params.values()
    assert datetime(2026, 6, 8, tzinfo=UTC) in params.values()
    assert "Phân tích 2 mẫu telemetry trong" in result
    assert "Thời điểm mẫu mới nhất: 15:00:00 ngày 07/06/2026 (giờ Việt Nam)" in result
    assert "trung bình 30.0°C" in result
    assert "thấp nhất 28.0°C; cao nhất 32.0°C" in result
    assert "trung bình 75.0%" in result


@pytest.mark.asyncio
async def test_telemetry_tool_reports_empty_time_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.react import ToolContext

    session = FakeTelemetrySession([[(0, None, None, None, None, None, None)], []])

    @asynccontextmanager
    async def fake_db_session() -> Any:
        yield session

    monkeypatch.setattr("agent.tools.telemetry.db_session", fake_db_session)

    result = await TelemetryTool().execute(
        TelemetryInput(relative_range="last_30_days"),
        ToolContext(goal="độ ẩm 1 tháng qua", user_id=7),
    )

    assert "trong 30 ngày qua" in result
    assert session.statements[0]._limit_clause is None


@pytest.mark.asyncio
async def test_telemetry_tool_queries_temperature_max_for_current_day_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.react import ToolContext

    row = (
        TelemetryModel(
            id=9,
            iot_node_id=1,
            timestamp=datetime(2026, 6, 23, 2, 0, tzinfo=UTC),
            temperature_celsius=35.2,
            humidity_percent=68,
        ),
        "Cảm biến 01",
        "Ruộng lúa",
    )
    session = FakeTelemetrySession([[row]])

    @asynccontextmanager
    async def fake_db_session() -> Any:
        yield session

    monkeypatch.setattr("agent.tools.telemetry.db_session", fake_db_session)
    monkeypatch.setattr(
        "agent.tools.telemetry.get_utc_now",
        lambda: datetime(2026, 6, 23, 3, 0, tzinfo=UTC),
    )

    result = await TelemetryTool().execute(
        TelemetryInput(query_kinds=["temperature_max"]),
        ToolContext(goal="nhiệt độ cao nhất là bao nhiêu?", user_id=7),
    )

    statement = session.statements[0]
    statement_text = str(statement)
    params = statement.compile().params
    assert "telemetry.temperature_celsius IS NOT NULL" in statement_text
    assert "telemetry.timestamp >= " in statement_text
    assert "telemetry.timestamp < " in statement_text
    assert "telemetry.temperature_celsius DESC" in statement_text
    assert "telemetry.timestamp DESC" in statement_text
    assert "telemetry.id DESC" in statement_text
    assert datetime(2026, 6, 22, 17, 0, tzinfo=UTC) in params.values()
    assert datetime(2026, 6, 23, 3, 0, tzinfo=UTC) in params.values()
    assert "Truy vấn telemetry theo chỉ số trong hôm nay" in result
    assert "Nhiệt độ cao nhất trong hôm nay: 35.2°C" in result
    assert "thời điểm 09:00:00 ngày 23/06/2026 (giờ Việt Nam)" in result
    assert "+00:00" not in result
    assert "thiết bị Cảm biến 01; mission Ruộng lúa" in result
    assert "trung bình" not in result
    assert "Độ ẩm" not in result


@pytest.mark.asyncio
async def test_telemetry_tool_queries_humidity_min_for_explicit_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.react import ToolContext

    row = (
        TelemetryModel(
            id=10,
            iot_node_id=1,
            timestamp=datetime(2026, 6, 4, 8, 0, tzinfo=UTC),
            temperature_celsius=30,
            humidity_percent=55.4,
        ),
        "Cảm biến 02",
        "Vườn tiêu",
    )
    session = FakeTelemetrySession([[row]])

    @asynccontextmanager
    async def fake_db_session() -> Any:
        yield session

    monkeypatch.setattr("agent.tools.telemetry.db_session", fake_db_session)

    result = await TelemetryTool().execute(
        TelemetryInput(
            query_kinds=["humidity_min"],
            start_time=datetime(2026, 6, 1, tzinfo=UTC),
            end_time=datetime(2026, 6, 8, tzinfo=UTC),
        ),
        ToolContext(goal="độ ẩm thấp nhất từ 1/6 đến 7/6", user_id=7),
    )

    statement_text = str(session.statements[0])
    assert "telemetry.humidity_percent IS NOT NULL" in statement_text
    assert "telemetry.humidity_percent ASC" in statement_text
    assert (
        "Độ ẩm thấp nhất từ 07:00:00 ngày 01/06/2026 (giờ Việt Nam) "
        "đến trước 07:00:00 ngày 08/06/2026 (giờ Việt Nam)"
    ) in result
    assert "55.4%" in result
    assert "thiết bị Cảm biến 02; mission Vườn tiêu" in result


@pytest.mark.asyncio
async def test_telemetry_tool_handles_multiple_specific_queries_and_no_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.react import ToolContext

    humidity_row = (
        TelemetryModel(
            id=11,
            iot_node_id=1,
            timestamp=datetime(2026, 6, 23, 4, 0, tzinfo=UTC),
            temperature_celsius=None,
            humidity_percent=82.3,
        ),
        "Cảm biến 03",
        "Nhà kính",
    )
    session = FakeTelemetrySession([[], [humidity_row]])

    @asynccontextmanager
    async def fake_db_session() -> Any:
        yield session

    monkeypatch.setattr("agent.tools.telemetry.db_session", fake_db_session)
    monkeypatch.setattr(
        "agent.tools.telemetry.get_utc_now",
        lambda: datetime(2026, 6, 23, 5, 0, tzinfo=UTC),
    )

    result = await TelemetryTool().execute(
        TelemetryInput(query_kinds=["temperature_min", "humidity_max"]),
        ToolContext(goal="nhiệt độ thấp nhất và độ ẩm cao nhất hôm nay", user_id=7),
    )

    assert len(session.statements) == 2
    assert "Không có dữ liệu nhiệt độ trong hôm nay" in result
    assert "Độ ẩm cao nhất trong hôm nay: 82.3%" in result
    assert "thời điểm 11:00:00 ngày 23/06/2026 (giờ Việt Nam)" in result
    assert "trung bình" not in result


@pytest.mark.asyncio
async def test_telemetry_tool_queries_temperature_max_for_two_hour_empty_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.react import ToolContext

    session = FakeTelemetrySession([[]])

    @asynccontextmanager
    async def fake_db_session() -> Any:
        yield session

    monkeypatch.setattr("agent.tools.telemetry.db_session", fake_db_session)
    monkeypatch.setattr(
        "agent.tools.telemetry.get_utc_now",
        lambda: datetime(2026, 6, 23, 9, 9, tzinfo=UTC),
    )

    result = await TelemetryTool().execute(
        TelemetryInput(
            query_kinds=["temperature_max"],
            temporal_intent=TelemetryTemporalIntent(
                kind="rolling",
                count=2,
                unit="hour",
            ),
        ),
        ToolContext(
            goal=(
                "trong hai tiếng vừa rồi nhiệt độ cao nhất là bao nhiêu "
                "và ở thời điểm nào"
            ),
            user_id=7,
        ),
    )

    statement = session.statements[0]
    params = statement.compile().params
    assert datetime(2026, 6, 23, 7, 9, tzinfo=UTC) in params.values()
    assert datetime(2026, 6, 23, 9, 9, tzinfo=UTC) in params.values()
    assert "Truy vấn telemetry theo chỉ số trong 2 giờ qua" in result
    assert "Không có dữ liệu nhiệt độ trong 2 giờ qua" in result
    assert "không hỗ trợ" not in result


@pytest.mark.asyncio
async def test_telemetry_tool_queries_temperature_at_nearest_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.react import ToolContext

    row = (
        TelemetryModel(
            id=12,
            iot_node_id=1,
            timestamp=datetime(2026, 6, 23, 5, 20, tzinfo=UTC),
            temperature_celsius=31.4,
            humidity_percent=70,
        ),
        "Cảm biến 04",
        "Ruộng lúa",
    )
    session = FakeTelemetrySession([[row]])

    @asynccontextmanager
    async def fake_db_session() -> Any:
        yield session

    monkeypatch.setattr("agent.tools.telemetry.db_session", fake_db_session)
    monkeypatch.setattr(
        "agent.tools.telemetry.get_utc_now",
        lambda: datetime(2026, 6, 23, 6, 0, tzinfo=UTC),
    )

    result = await TelemetryTool().execute(
        TelemetryInput(query_kinds=["temperature_at"]),
        ToolContext(goal="nhiệt độ lúc 12:18 23-06 là bao nhiêu", user_id=7),
    )

    statement = session.statements[0]
    statement_text = str(statement)
    params = statement.compile().params
    assert "telemetry.temperature_celsius IS NOT NULL" in statement_text
    assert "telemetry.timestamp >= " in statement_text
    assert "telemetry.timestamp <= " in statement_text
    assert "ORDER BY abs" in statement_text
    assert datetime(2026, 6, 23, 5, 13, tzinfo=UTC) in params.values()
    assert datetime(2026, 6, 23, 5, 23, tzinfo=UTC) in params.values()
    assert "Truy vấn telemetry tại thời điểm 12:18:00 ngày 23/06/2026" in result
    assert "Nhiệt độ gần 12:18:00 ngày 23/06/2026" in result
    assert "31.4°C" in result
    assert "mẫu thực tế 12:20:00 ngày 23/06/2026" in result
    assert "lệch 2 phút" in result
    assert "thiết bị Cảm biến 04; mission Ruộng lúa" in result


@pytest.mark.asyncio
async def test_telemetry_tool_point_lookup_defaults_missing_date_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.react import ToolContext

    row = (
        TelemetryModel(
            id=13,
            iot_node_id=1,
            timestamp=datetime(2026, 6, 23, 5, 18, tzinfo=UTC),
            temperature_celsius=30.1,
            humidity_percent=71.2,
        ),
        "Cảm biến 05",
        "Nhà kính",
    )
    session = FakeTelemetrySession([[row]])

    @asynccontextmanager
    async def fake_db_session() -> Any:
        yield session

    monkeypatch.setattr("agent.tools.telemetry.db_session", fake_db_session)
    monkeypatch.setattr(
        "agent.tools.telemetry.get_utc_now",
        lambda: datetime(2026, 6, 23, 6, 0, tzinfo=UTC),
    )

    result = await TelemetryTool().execute(
        TelemetryInput(query_kinds=["humidity_at"]),
        ToolContext(goal="độ ẩm lúc 12:18 là bao nhiêu", user_id=7),
    )

    params = session.statements[0].compile().params
    assert datetime(2026, 6, 23, 5, 13, tzinfo=UTC) in params.values()
    assert datetime(2026, 6, 23, 5, 23, tzinfo=UTC) in params.values()
    assert "Độ ẩm gần 12:18:00 ngày 23/06/2026" in result
    assert "71.2%" in result


@pytest.mark.asyncio
async def test_telemetry_tool_point_lookup_reports_no_nearby_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.react import ToolContext

    session = FakeTelemetrySession([[]])

    @asynccontextmanager
    async def fake_db_session() -> Any:
        yield session

    monkeypatch.setattr("agent.tools.telemetry.db_session", fake_db_session)
    monkeypatch.setattr(
        "agent.tools.telemetry.get_utc_now",
        lambda: datetime(2026, 6, 23, 6, 0, tzinfo=UTC),
    )

    result = await TelemetryTool().execute(
        TelemetryInput(query_kinds=["temperature_at"]),
        ToolContext(goal="nhiệt độ lúc 12:18 ngày 23 là bao nhiêu", user_id=7),
    )

    assert "Không có dữ liệu nhiệt độ trong ±5 phút quanh" in result
    assert "12:18:00 ngày 23/06/2026" in result


@pytest.mark.asyncio
async def test_search_tool_filters_trace_regression_noise() -> None:
    from agent.react import ToolContext

    class FakeClient:
        def search(self, *, query: str, max_results: int) -> dict[str, Any]:
            return {
                "results": [
                    {
                        "title": "Weather for Gia Lai",
                        "content": "Gia Lai has rain and moderate humidity today.",
                        "url": "https://example.com/weather",
                    },
                    {
                        "title": "EPR compliance update",
                        "content": "Packaging rules for manufacturers.",
                        "url": "https://example.com/epr",
                    },
                ]
            }

    class TraceFilter:
        async def filter(self, data: Any) -> SearchFilterDecision:
            return SearchFilterDecision(
                coverage="partial",
                relevant_results=[
                    FilteredSearchResult(
                        title="Weather for Gia Lai",
                        url="https://example.com/weather",
                        summary="Gia Lai has rain and moderate humidity today.",
                        usable_claims=[
                            UsableClaim(
                                claim="Rain and moderate humidity are expected.",
                                source_url="https://example.com/weather",
                            )
                        ],
                        relevance_reason="Weather source matches the location.",
                    )
                ],
                rejected_results=[
                    RejectedSearchResult(
                        title="EPR compliance update",
                        url="https://example.com/epr",
                        reason="EPR compliance is unrelated to weather.",
                    )
                ],
            )

    tool = SearchTool.__new__(SearchTool)
    tool._client = FakeClient()
    setattr(tool, "_result_filter", TraceFilter())

    result = await tool.execute(
        SearchInput(query="weather Gia Lai", max_results=2),
        ToolContext(goal="search"),
    )

    assert "Weather for Gia Lai" in result
    assert "Rain and moderate humidity are expected." in result
    assert "EPR compliance update" not in result
    assert "https://example.com/epr" not in result


def test_system_prompt_requires_search_source_links() -> None:
    assert "numbered inline citation links" in SYSTEM_PROMPT
    assert "Do not add a separate" in SYSTEM_PROMPT


def test_react_prompt_limits_thought() -> None:
    from agent.prompts import REACT_PROMPT

    assert "one short sentence" in REACT_PROMPT


def test_structured_output_uses_json_mode_when_supported() -> None:
    class FakeStructuredLLM:
        pass

    class FakeLLM:
        def __init__(self) -> None:
            self.schema: Any = None
            self.method: str | None = None

        def with_structured_output(self, schema: Any, *, method: str) -> Any:
            self.schema = schema
            self.method = method
            return FakeStructuredLLM()

    llm = FakeLLM()

    bound = bind_structured_output(llm, ReasoningDecision)

    assert isinstance(bound, FakeStructuredLLM)
    assert llm.schema is ReasoningDecision
    assert llm.method == "json_mode"


def test_structured_prompts_require_json_only() -> None:
    from agent.prompts import REACT_PROMPT, TOOL_POLICY_PROMPT

    assert "Return\nvalid JSON only" in REACT_PROMPT
    assert "Do not wrap in" in REACT_PROMPT
    assert "Return valid JSON only" in TOOL_POLICY_PROMPT
    assert "Do not wrap in" in TOOL_POLICY_PROMPT


@pytest.mark.asyncio
async def test_llm_reasoner_recovers_valid_json_from_raw_content_list() -> None:
    class FakeBoundLLM:
        async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
            return SimpleNamespace(
                content=[
                    'thought":"broken prefix',
                    (
                        '{"thought":"Recovered.","action":null,'
                        '"is_done":true,"final_answer":"Đã có câu trả lời."}'
                    ),
                ]
            )

    class FakeLLM:
        def __init__(self) -> None:
            self.bound_kwargs: dict[str, Any] = {}

        def bind(self, **kwargs: Any) -> Any:
            self.bound_kwargs = kwargs
            return FakeBoundLLM()

    llm = FakeLLM()
    reasoner = LLMReasoner(llm, timeout_seconds=1)

    decision = await reasoner.decide("Trả lời ngắn", InMemoryMemory(), [])

    assert llm.bound_kwargs["response_mime_type"] == "application/json"
    assert llm.bound_kwargs["response_schema"]["title"] == "ReasoningDecision"
    assert decision.is_done is True
    assert decision.final_answer == "Đã có câu trả lời."


def test_structured_parsers_accept_pydantic_dict_and_raw_content() -> None:
    reasoner_decision = ReasoningDecision(
        thought="Done.",
        is_done=True,
        final_answer="Hoàn tất.",
    )
    assert _parse_reasoning_decision(reasoner_decision) == reasoner_decision
    assert (
        _parse_reasoning_decision(
            {
                "parsed": {
                    "thought": "Done.",
                    "action": None,
                    "is_done": True,
                    "final_answer": "Hoàn tất.",
                }
            }
        ).final_answer
        == "Hoàn tất."
    )
    assert (
        _parse_reasoning_decision(
            SimpleNamespace(
                content=(
                    '{"thought":"Done.","action":null,'
                    '"is_done":true,"final_answer":"Hoàn tất."}'
                )
            )
        ).is_done
        is True
    )

    route_decision = FallbackRouteDecision(
        tool="none",
        input={},
        reason="No tool needed.",
    )
    assert _parse_fallback_route_decision(route_decision) == route_decision
    assert (
        _parse_fallback_route_decision(
            SimpleNamespace(
                content='{"tool":"none","input":{},"reason":"No tool needed."}'
            )
        ).tool
        == "none"
    )

    assert (
        _parse_tool_policy_decision(
            SimpleNamespace(content='{"actions":[],"rationale":"No tool needed."}')
        ).rationale
        == "No tool needed."
    )
    tool_policy_decision = _parse_tool_policy_decision(
        SimpleNamespace(
            content=(
                '{"actions":[{"tool":"telemetry","input":{"query_kinds":'
                '["temperature_max"],"relative_range":"today"}}]}'
            )
        )
    )
    assert tool_policy_decision.rationale == (
        "No rationale provided by policy classifier."
    )
    assert tool_policy_decision.actions[0].reason == (
        "Tool selected by policy classifier."
    )

    assert (
        _parse_filter_decision(
            SimpleNamespace(
                content=(
                    '{"coverage":"insufficient","relevant_results":[],'
                    '"rejected_results":[]}'
                )
            )
        ).coverage
        == "insufficient"
    )


@pytest.mark.asyncio
async def test_llm_reasoner_retries_retryable_llm_errors() -> None:
    class FakeBoundLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise RateLimitError
            return {
                "thought": "Recovered.",
                "action": None,
                "is_done": True,
                "final_answer": "Đã thử lại thành công.",
            }

    class FakeLLM:
        def __init__(self) -> None:
            self.bound = FakeBoundLLM()

        def bind(self, **kwargs: Any) -> Any:
            return self.bound

    llm = FakeLLM()
    reasoner = LLMReasoner(
        llm,
        timeout_seconds=1,
        max_retries=1,
        backoff_seconds=0,
    )

    decision = await reasoner.decide("Trả lời ngắn", InMemoryMemory(), [])

    assert llm.bound.calls == 2
    assert decision.final_answer == "Đã thử lại thành công."


@pytest.mark.asyncio
async def test_search_result_filter_retries_retryable_llm_errors() -> None:
    class FakeBoundLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise RateLimitError
            return {
                "coverage": "sufficient",
                "relevant_results": [
                    {
                        "title": "Rice market",
                        "url": "https://example.com/rice",
                        "summary": "Rice prices increased.",
                        "usable_claims": [
                            {
                                "claim": "Rice prices increased.",
                                "source_url": "https://example.com/rice",
                            }
                        ],
                        "relevance_reason": "Directly relevant.",
                    }
                ],
                "rejected_results": [],
            }

    class FakeLLM:
        def __init__(self) -> None:
            self.bound = FakeBoundLLM()

        def bind(self, **kwargs: Any) -> Any:
            return self.bound

    llm = FakeLLM()
    result_filter = SearchResultFilter(
        llm,
        timeout_seconds=1,
        max_retries=1,
        backoff_seconds=0,
    )

    decision = await result_filter.filter(
        SearchFilterInput(
            question="rice price",
            results=[
                {
                    "title": "Rice market",
                    "url": "https://example.com/rice",
                    "content": "Rice prices increased.",
                }
            ],
        )
    )

    assert llm.bound.calls == 2
    assert decision.coverage == "sufficient"
    assert decision.relevant_results[0].url == "https://example.com/rice"


@pytest.mark.asyncio
async def test_llm_routed_fallback_formats_search_results_as_citations() -> None:
    memory = InMemoryMemory()
    memory.add(
        ReActStep(
            thought="Use search.",
            action=Action(tool="search", input={"query": "chăm sóc hồ tiêu Gia Lai"}),
            observation=(
                "- Title: HƯỚNG DẪN QUY TRÌNH TRỒNG VÀ CHĂM SÓC CÂY HỒ TIÊU\n"
                "  URL: https://example.com/ho-tieu\n"
                "  Snippet: Trước khi trồng cần chuẩn bị đất và bón lót phân "
                "chuồng hoai.\n\n"
                "- Title: Chăm sóc cây hồ tiêu vào mùa mưa\n"
                "  URL: https://example.com/mua-mua\n"
                "  Snippet: Cần kiểm soát thoát nước và bổ sung hữu cơ."
            ),
        )
    )
    reasoner = LLMRoutedFallbackReasoner(None)

    answer = await reasoner.finalize("Gợi ý chăm sóc hồ tiêu tại Gia Lai", memory)

    assert "Thông tin nổi bật" in answer
    assert "[1](https://example.com/ho-tieu)" in answer
    assert "Nguồn tham khảo" not in answer
    assert "Title:" not in answer
    assert "URL:" not in answer
    assert "Snippet:" not in answer


@pytest.mark.asyncio
async def test_provider_fallback_uses_llm_router_selected_search() -> None:
    class FailingReasoner:
        async def decide(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> ReasoningDecision:
            raise TimeoutError

        async def finalize(self, goal: str, memory: Memory) -> str:
            raise TimeoutError

    class FakeRouter(LLMToolRouter):
        def __init__(self) -> None:
            pass

        async def route(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> FallbackRouteDecision:
            return FallbackRouteDecision(
                tool="search",
                input={"query": goal, "max_results": 3},
                reason="Needs web evidence.",
            )

    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )
    reasoner = FallbackReasoner(
        FailingReasoner(),
        LLMRoutedFallbackReasoner(FakeRouter()),
    )

    decision = await reasoner.decide(
        "chăm sóc hồ tiêu mùa mưa", InMemoryMemory(), (search_tool,)
    )

    assert decision.action == Action(
        tool="search",
        input={"query": "chăm sóc hồ tiêu mùa mưa", "max_results": 3},
    )


@pytest.mark.asyncio
async def test_provider_fallback_propagates_router_failure() -> None:
    class FailingReasoner:
        async def decide(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> ReasoningDecision:
            raise TimeoutError

        async def finalize(self, goal: str, memory: Memory) -> str:
            raise TimeoutError

    class FailingRouter(LLMToolRouter):
        def __init__(self) -> None:
            pass

        async def route(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> FallbackRouteDecision:
            raise TimeoutError

    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )
    reasoner = FallbackReasoner(
        FailingReasoner(),
        LLMRoutedFallbackReasoner(FailingRouter()),
    )

    with pytest.raises(TimeoutError):
        await reasoner.decide("khuyến nghị tưới tiêu", InMemoryMemory(), (search_tool,))


@pytest.mark.asyncio
async def test_semantic_tool_policy_uses_user_telemetry_before_search() -> None:
    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    telemetry_tool = CallableTool(
        "telemetry",
        "Read recent temperature and humidity owned by the user.",
        handler,
        input_model=TelemetryInput,
    )
    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )
    question = "Thời tiết tuần này ảnh hưởng thế nào đến lịch canh tác?"
    llm = FakePolicyLLM(
        {
            "actions": [
                {
                    "tool": "telemetry",
                    "input": {"limit": 50},
                    "reason": "Needs first-party field conditions.",
                },
                {
                    "tool": "search",
                    "input": {
                        "query": question,
                        "max_results": 5,
                    },
                    "reason": "Needs external forecast.",
                },
            ],
            "rationale": "Use telemetry before external forecast.",
        }
    )
    policy = SemanticToolPolicy(llm, timeout_seconds=1)

    decision = await policy.decide(
        question,
        InMemoryMemory(),
        (search_tool, telemetry_tool),
    )

    assert decision == Action(tool="telemetry", input={"limit": 50})
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_semantic_tool_policy_accepts_telemetry_relative_range() -> None:
    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    telemetry_tool = CallableTool(
        "telemetry",
        "Read temperature and humidity owned by the user with time filters.",
        handler,
        input_model=TelemetryInput,
    )
    question = "Độ ẩm 1 tuần qua biến động thế nào?"
    llm = FakePolicyLLM(
        {
            "actions": [
                {
                    "tool": "telemetry",
                    "input": {"relative_range": "last_7_days"},
                    "reason": "Needs first-party telemetry over the requested period.",
                }
            ],
            "rationale": "Use telemetry with the requested period.",
        }
    )
    policy = SemanticToolPolicy(llm, timeout_seconds=1)

    decision = await policy.decide(question, InMemoryMemory(), (telemetry_tool,))

    assert decision == Action(
        tool="telemetry",
        input={"limit": 50, "relative_range": "last_7_days"},
    )


@pytest.mark.asyncio
async def test_semantic_tool_policy_accepts_telemetry_temporal_intent() -> None:
    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    telemetry_tool = CallableTool(
        "telemetry",
        "Read temperature and humidity owned by the user with time filters.",
        handler,
        input_model=TelemetryInput,
    )
    question = "trong hai tiếng vừa rồi nhiệt độ cao nhất là bao nhiêu?"
    llm = FakePolicyLLM(
        {
            "actions": [
                {
                    "tool": "telemetry",
                    "input": {
                        "query_kinds": ["temperature_max"],
                        "temporal_intent": {
                            "kind": "rolling",
                            "count": 2,
                            "unit": "hour",
                        },
                    },
                    "reason": "Needs max first-party telemetry over a rolling range.",
                }
            ],
            "rationale": "Use telemetry with structured temporal intent.",
        }
    )
    policy = SemanticToolPolicy(llm, timeout_seconds=1)

    decision = await policy.decide(question, InMemoryMemory(), (telemetry_tool,))

    assert decision == Action(
        tool="telemetry",
        input={
            "limit": 50,
            "query_kinds": ["temperature_max"],
            "temporal_intent": {"kind": "rolling", "count": 2, "unit": "hour"},
        },
    )


@pytest.mark.asyncio
async def test_semantic_tool_policy_accepts_telemetry_specific_query_kinds() -> None:
    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    telemetry_tool = CallableTool(
        "telemetry",
        "Read temperature and humidity owned by the user with time filters.",
        handler,
        input_model=TelemetryInput,
    )
    question = "Nhiệt độ cao nhất hôm nay là bao nhiêu?"
    llm = FakePolicyLLM(
        {
            "actions": [
                {
                    "tool": "telemetry",
                    "input": {
                        "query_kinds": ["temperature_max"],
                        "relative_range": "today",
                    },
                    "reason": "Needs the exact highest first-party temperature today.",
                }
            ],
            "rationale": "Use telemetry for exact max value.",
        }
    )
    policy = SemanticToolPolicy(llm, timeout_seconds=1)

    decision = await policy.decide(question, InMemoryMemory(), (telemetry_tool,))

    assert decision == Action(
        tool="telemetry",
        input={
            "limit": 50,
            "query_kinds": ["temperature_max"],
            "relative_range": "today",
        },
    )


@pytest.mark.asyncio
async def test_semantic_tool_policy_accepts_missing_observability_metadata() -> None:
    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    telemetry_tool = CallableTool(
        "telemetry",
        "Read temperature and humidity owned by the user with time filters.",
        handler,
        input_model=TelemetryInput,
    )
    llm = FakePolicyLLM(
        {
            "actions": [
                {
                    "tool": "telemetry",
                    "input": {
                        "query_kinds": ["temperature_max"],
                        "relative_range": "today",
                    },
                }
            ],
        }
    )
    policy = SemanticToolPolicy(llm, timeout_seconds=1)

    decision = await policy.decide(
        "Nhiệt độ cao nhất hôm nay là bao nhiêu?",
        InMemoryMemory(),
        (telemetry_tool,),
    )

    assert decision == Action(
        tool="telemetry",
        input={
            "limit": 50,
            "query_kinds": ["temperature_max"],
            "relative_range": "today",
        },
    )


@pytest.mark.asyncio
async def test_semantic_tool_policy_accepts_telemetry_point_query_kind() -> None:
    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    telemetry_tool = CallableTool(
        "telemetry",
        "Read temperature and humidity owned by the user with time filters.",
        handler,
        input_model=TelemetryInput,
    )
    question = "nhiệt độ lúc 12:18 23-06 là bao nhiêu"
    llm = FakePolicyLLM(
        {
            "actions": [
                {
                    "tool": "telemetry",
                    "input": {"query_kinds": ["temperature_at"]},
                    "reason": "Needs first-party temperature near the requested time.",
                }
            ],
            "rationale": "Use telemetry for point-in-time temperature.",
        }
    )
    policy = SemanticToolPolicy(llm, timeout_seconds=1)

    decision = await policy.decide(question, InMemoryMemory(), (telemetry_tool,))

    assert decision == Action(
        tool="telemetry",
        input={"limit": 50, "query_kinds": ["temperature_at"]},
    )


@pytest.mark.asyncio
async def test_semantic_tool_policy_adds_forecast_search_after_telemetry() -> None:
    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    telemetry_tool = CallableTool(
        "telemetry",
        "Read recent temperature and humidity owned by the user.",
        handler,
        input_model=TelemetryInput,
    )
    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )
    memory = InMemoryMemory()
    memory.add(
        ReActStep(
            thought="Use telemetry.",
            action=Action(tool="telemetry", input={"limit": 50}),
            observation="Nhiệt độ mới nhất 31°C.",
        )
    )
    question = "Thời tiết tuần này ảnh hưởng thế nào đến lịch canh tác?"
    llm = FakePolicyLLM(
        {
            "actions": [
                {
                    "tool": "telemetry",
                    "input": {"limit": 50},
                    "reason": "Needs first-party field conditions.",
                },
                {
                    "tool": "search",
                    "input": {
                        "query": question,
                        "max_results": 5,
                    },
                    "reason": "Needs external forecast.",
                },
            ],
            "rationale": "Use telemetry first, then forecast.",
        }
    )
    policy = SemanticToolPolicy(llm, timeout_seconds=1)

    decision = await policy.decide(
        question,
        memory,
        (search_tool, telemetry_tool),
    )

    assert decision == Action(
        tool="search",
        input={
            "query": question,
            "max_results": 5,
        },
    )


@pytest.mark.asyncio
async def test_llm_tool_router_retries_retryable_llm_errors() -> None:
    class FakeBoundLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise RateLimitError
            return {
                "tool": "search",
                "input": {"query": "hồ tiêu", "max_results": 2},
                "reason": "Needs current web information.",
            }

    class FakeLLM:
        def __init__(self) -> None:
            self.bound = FakeBoundLLM()

        def bind(self, **kwargs: Any) -> Any:
            return self.bound

    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )
    llm = FakeLLM()
    router = LLMToolRouter(
        llm,
        timeout_seconds=1,
        max_retries=1,
        backoff_seconds=0,
    )

    decision = await router.route("hồ tiêu", InMemoryMemory(), (search_tool,))

    assert llm.bound.calls == 2
    assert decision.tool == "search"
    assert decision.input == {"query": "hồ tiêu", "max_results": 2}


@pytest.mark.asyncio
async def test_llm_routed_fallback_uses_calculator_when_router_input_is_valid() -> None:
    class FakeRouter(LLMToolRouter):
        def __init__(self) -> None:
            pass

        async def route(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> FallbackRouteDecision:
            return FallbackRouteDecision(
                tool="calculator",
                input={"expression": "6 * 7"},
                reason="Pure arithmetic.",
            )

    reasoner = LLMRoutedFallbackReasoner(FakeRouter())

    decision = await reasoner.decide("6 * 7", InMemoryMemory(), (CalculatorTool(),))

    assert decision.action == Action(
        tool="calculator",
        input={"expression": "6 * 7"},
    )


@pytest.mark.asyncio
async def test_llm_routed_fallback_returns_error_for_invalid_router_input() -> None:
    class FakeRouter(LLMToolRouter):
        def __init__(self) -> None:
            pass

        async def route(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> FallbackRouteDecision:
            return FallbackRouteDecision(
                tool="calculator",
                input={"expression": ""},
                reason="Invalid calculator input.",
            )

    reasoner = LLMRoutedFallbackReasoner(FakeRouter())

    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )

    decision = await reasoner.decide(
        "thông tin canh tác mới", InMemoryMemory(), (search_tool, CalculatorTool())
    )

    assert decision.is_done is True
    assert decision.final_answer is not None
    assert "Không thể thu thập dữ liệu" in decision.final_answer


@pytest.mark.asyncio
async def test_llm_routed_fallback_raises_when_router_fails() -> None:
    class FailingRouter(LLMToolRouter):
        def __init__(self) -> None:
            pass

        async def route(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> FallbackRouteDecision:
            raise TimeoutError

    reasoner = LLMRoutedFallbackReasoner(FailingRouter())

    async def handler(tool_input: Any, context: Any) -> str:
        return "unused"

    search_tool = CallableTool(
        "search",
        "Search web",
        handler,
        input_model=SearchInput,
    )

    with pytest.raises(TimeoutError):
        await reasoner.decide("khuyến nghị tưới tiêu", InMemoryMemory(), (search_tool,))


@pytest.mark.asyncio
async def test_llm_routed_fallback_without_search_raises_router_error() -> None:
    class FailingRouter(LLMToolRouter):
        def __init__(self) -> None:
            pass

        async def route(
            self,
            goal: str,
            memory: Memory,
            tools: Sequence[Tool],
        ) -> FallbackRouteDecision:
            raise TimeoutError

    reasoner = LLMRoutedFallbackReasoner(FailingRouter())

    with pytest.raises(TimeoutError):
        await reasoner.decide("câu hỏi mở", InMemoryMemory(), (CalculatorTool(),))


@pytest.mark.asyncio
async def test_run_agent_forwards_bounded_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_memory: Any = None
    seen_session_id: str | None = None

    class FakeAgent:
        async def run(self, goal: str, **kwargs: Any) -> AgentLoopResult:
            nonlocal seen_memory, seen_session_id
            seen_memory = kwargs["memory"]
            seen_session_id = kwargs["session_id"]
            return AgentLoopResult("answer", True, 1, (), "done", "run")

    monkeypatch.setattr("agent.agent.default_agent", FakeAgent())
    answer = await run_agent(
        "question",
        user_id=7,
        session_id="chat-42",
        history=[ConversationMessage(role="user", content="previous")],
    )
    assert answer == "answer"
    assert seen_memory.conversation()[0].content == "previous"
    assert seen_session_id == "chat-42"


@pytest.mark.asyncio
async def test_stream_agent_emits_live_tool_status_and_incremental_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAgent:
        async def run(self, goal: str, **kwargs: Any) -> AgentLoopResult:
            from agent.react import AgentEvent

            await kwargs["on_event"](
                AgentEvent("tool_started", "run", 1, tool="search")
            )
            return AgentLoopResult(
                "abcdefghijklmnopqrstuvwxyz0123456789",
                True,
                1,
                (),
                "done",
                "run",
            )

    monkeypatch.setattr("agent.agent.default_agent", FakeAgent())
    events = [event async for event in stream_agent("question", user_id=7)]
    assert events[0]["phase"] == "routing"
    assert events[1]["tool"] == "search"
    assert events[2]["phase"] == "synthesis"
    tokens = [event["content"] for event in events if event["event"] == "token"]
    assert len(tokens) == 2
    assert "".join(tokens) == "abcdefghijklmnopqrstuvwxyz0123456789"


@pytest.mark.asyncio
async def test_stream_agent_does_not_generate_final_answer_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnexpectedStreamingReasoner:
        async def stream_finalize(self, *args: Any) -> Any:
            if False:
                yield ""
            raise AssertionError("final answer must not be generated twice")

    class FakeAgent:
        loop = SimpleNamespace(reasoner=UnexpectedStreamingReasoner())

        async def run(self, goal: str, **kwargs: Any) -> AgentLoopResult:
            return AgentLoopResult("single final answer", True, 1, (), "done", "run")

    monkeypatch.setattr("agent.agent.default_agent", FakeAgent())
    events = [event async for event in stream_agent("question")]

    assert (
        "".join(event["content"] for event in events if event["event"] == "token")
        == "single final answer"
    )


@pytest.mark.asyncio
async def test_stream_agent_cancels_background_task_when_client_disconnects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class BlockingAgent:
        async def run(self, goal: str, **kwargs: Any) -> AgentLoopResult:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            raise AssertionError("blocking agent unexpectedly completed")

    monkeypatch.setattr("agent.agent.default_agent", BlockingAgent())
    events = stream_agent("question")

    assert (await anext(events))["phase"] == "routing"
    await asyncio.wait_for(started.wait(), timeout=1)
    close_stream = getattr(events, "aclose")
    await close_stream()

    await asyncio.wait_for(cancelled.wait(), timeout=1)


def test_classify_llm_error_rate_limit_by_status_code() -> None:
    result = classify_llm_error(RateLimitError())
    assert result.error_code == "rate_limit"
    assert result.http_status == 503


def test_classify_llm_error_rate_limit_by_message() -> None:
    result = classify_llm_error(RuntimeError("429 rate limit exceeded"))
    assert result.error_code == "rate_limit"
    assert result.http_status == 503


def test_classify_llm_error_timeout() -> None:
    result = classify_llm_error(TimeoutError())
    assert result.error_code == "timeout"
    assert result.http_status == 504


def test_classify_llm_error_provider_unavailable() -> None:
    class ServerError(Exception):
        status_code = 503

    result = classify_llm_error(ServerError())
    assert result.error_code == "provider_unavailable"
    assert result.http_status == 503


def test_classify_llm_error_deadline_exceeded_maps_to_timeout() -> None:
    class DeadlineError(Exception):
        code = "DEADLINE_EXCEEDED"

    result = classify_llm_error(DeadlineError())
    assert result.error_code == "timeout"
    assert result.http_status == 504


def test_retryable_markers_cover_same_set_as_classify() -> None:
    from agent.reasoners import (
        _LLM_RETRYABLE_MESSAGE_MARKERS,
        _RATE_LIMIT_MARKERS,
        _UNAVAILABLE_MARKERS,
    )

    assert set(_LLM_RETRYABLE_MESSAGE_MARKERS) == set(_RATE_LIMIT_MARKERS) | set(
        _UNAVAILABLE_MARKERS
    )


def test_classify_llm_error_connection() -> None:
    result = classify_llm_error(ConnectionError("network unreachable"))
    assert result.error_code == "service_unavailable"
    assert result.http_status == 503


def test_classify_llm_error_generic_falls_back_to_internal() -> None:
    result = classify_llm_error(ValueError("unexpected value"))
    assert result.error_code == "internal_error"
    assert result.http_status == 500


def test_classify_llm_error_message_does_not_leak_details() -> None:
    result = classify_llm_error(RuntimeError("secret internal key abc123"))
    assert "abc123" not in result.message
    assert "secret" not in result.message


def test_llm_error_metadata_includes_sanitized_bad_request_details() -> None:
    class BadRequestError(Exception):
        status_code = 400
        body = {
            "error": {
                "type": "invalid_request_error",
                "message": (
                    "Invalid request. api_key=sk-secret-token "
                    "Structured output not supported."
                ),
            }
        }

    metadata = _llm_error_metadata(BadRequestError())

    assert metadata["status_code"] == 400
    assert metadata["provider_code"] == "invalid_request_error"
    assert metadata["provider_message"] == (
        "Invalid request. api_key=[redacted] Structured output not supported."
    )
    assert "sk-secret-token" not in metadata["provider_message"]


def test_extract_server_retry_delay_from_human_readable_message() -> None:
    exc = RuntimeError(
        "429 RESOURCE_EXHAUSTED. Please retry in 28.823862733s after the quota resets."
    )
    assert _extract_server_retry_delay(exc) == pytest.approx(28.823862733)


def test_extract_server_retry_delay_from_structured_detail() -> None:
    exc = RuntimeError("{'retryDelay': '53s', 'reason': 'provider throttled'}")
    assert _extract_server_retry_delay(exc) == pytest.approx(53.0)


def test_extract_server_retry_delay_returns_none_when_absent() -> None:
    assert _extract_server_retry_delay(RuntimeError("quota exceeded")) is None
    assert _extract_server_retry_delay(RateLimitError()) is None


@pytest.mark.asyncio
async def test_ainvoke_llm_with_retry_uses_server_delay_under_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retry should sleep for the server-suggested delay, not the fixed backoff."""
    from agent.reasoners import _ainvoke_llm_with_retry

    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = 0

    async def invoke() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("429 quota exceeded. Please retry in 2s.")
        return "ok"

    result = await _ainvoke_llm_with_retry(
        invoke,
        operation="test",
        timeout_seconds=5,
        max_retries=1,
        backoff_seconds=0.5,
    )

    assert result == "ok"
    assert calls == 2
    assert len(slept) == 1
    assert slept[0] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_ainvoke_llm_with_retry_caps_server_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server delay above the cap should be clamped."""
    from agent.reasoners import _ainvoke_llm_with_retry

    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = 0

    async def invoke() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("429 quota exceeded. Please retry in 999s.")
        return "ok"

    await _ainvoke_llm_with_retry(
        invoke,
        operation="test",
        timeout_seconds=5,
        max_retries=1,
        backoff_seconds=0.5,
    )

    assert slept[0] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_ainvoke_llm_with_retry_caps_server_delay_to_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server delay should never exceed the per-call request timeout."""
    from agent.reasoners import _ainvoke_llm_with_retry

    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = 0

    async def invoke() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("429 quota exceeded. Please retry in 4s.")
        return "ok"

    await _ainvoke_llm_with_retry(
        invoke,
        operation="test",
        timeout_seconds=1.5,
        max_retries=1,
        backoff_seconds=0.5,
    )

    assert slept[0] == pytest.approx(1.5)


@pytest.mark.asyncio
async def test_ainvoke_llm_with_retry_falls_back_to_backoff_without_server_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no server delay hint, exponential backoff should be used."""
    from agent.reasoners import _ainvoke_llm_with_retry

    slept: list[float] = []

    async def fake_sleep(s: float) -> None:
        slept.append(s)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    calls = 0

    async def invoke() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RateLimitError()
        return "ok"

    await _ainvoke_llm_with_retry(
        invoke,
        operation="test",
        timeout_seconds=5,
        max_retries=1,
        backoff_seconds=1.5,
    )

    assert slept[0] == pytest.approx(1.5)


@pytest.mark.skipif(
    os.getenv("RUN_AGENT_INTEGRATION_TESTS") != "1",
    reason="Set RUN_AGENT_INTEGRATION_TESTS=1 to call DeepSeek.",
)
@pytest.mark.asyncio
async def test_deepseek_agent_integration_opt_in() -> None:
    answer = await run_agent("Trả lời ngắn gọn: 2 + 2 bằng bao nhiêu?")
    assert answer.strip()
