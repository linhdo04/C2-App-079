from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException

from agent.pricing import estimate_cost_usd, resolve_model_pricing
from agent.run_metrics import record_agent_run_metric
from agent.tracing import AgentTraceContext, reset_trace_context, set_trace_context
from agent.usage import record_llm_usage
from api.dependencies import require_admin_user
from api.routes.admin_routes import (
    CostBudgetUpdateRequest,
    _baseline_range,
    _budget_public,
    _normalize_range,
    _projection_multiplier,
    get_cost_summary,
    get_evaluation_metrics,
    get_user_monthly_report,
    list_cost_usage,
    update_cost_budget,
)
from models.llm_usage import AgentRunMetricModel, CostBudgetModel, LLMUsageEventModel
from models.user import UserModel, UserRole


class FakeScalarResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class FakeResult:
    def __init__(
        self,
        *,
        one_row: tuple[Any, ...] | None = None,
        all_rows: list[Any] | None = None,
        scalars: list[Any] | None = None,
        scalar: Any | None = None,
    ) -> None:
        self._one_row = one_row
        self._all_rows = all_rows or []
        self._scalars = scalars or []
        self._scalar = scalar

    def one(self) -> tuple[Any, ...]:
        assert self._one_row is not None
        return self._one_row

    def all(self) -> list[Any]:
        return self._all_rows

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self._scalars)

    def scalar_one_or_none(self) -> Any:
        return self._scalar


class FakeSession:
    def __init__(self, results: list[FakeResult]) -> None:
        self.results = results
        self.statements: list[Any] = []
        self.added: list[Any] = []

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return self.results.pop(0)

    def add(self, value: Any) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        for value in self.added:
            if getattr(value, "id", None) is None:
                value.id = 1

    async def refresh(self, value: Any) -> None:
        return None


def user_factory(role: UserRole = UserRole.OPERATOR) -> UserModel:
    return UserModel(
        id=7,
        name="Admin",
        email="admin@example.com",
        password_hash="hash",
        role=role,
    )


@pytest.mark.asyncio
async def test_require_admin_user_rejects_operator() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_admin_user(user_factory(UserRole.OPERATOR))

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_user_accepts_admin() -> None:
    user = user_factory(UserRole.ADMIN)

    assert await require_admin_user(user) is user


def test_normalize_range_defaults_to_current_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api.routes.admin_routes.get_utc_now",
        lambda: datetime(2026, 6, 24, 10, 0, tzinfo=UTC),
    )

    start, end = _normalize_range(None, None)

    assert start == datetime(2026, 5, 31, 17, 0, tzinfo=UTC)
    assert end == datetime(2026, 6, 30, 17, 0, tzinfo=UTC)


def test_baseline_range_uses_previous_equal_duration() -> None:
    start = datetime(2026, 6, 10, tzinfo=UTC)
    end = datetime(2026, 6, 17, tzinfo=UTC)

    baseline_start, baseline_end = _baseline_range(start, end)

    assert baseline_start == datetime(2026, 6, 3, tzinfo=UTC)
    assert baseline_end == start


def test_projection_multiplier_current_month_to_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api.routes.admin_routes.get_utc_now",
        lambda: datetime(2026, 6, 15, 17, 0, tzinfo=UTC),
    )
    month_start, month_end = _normalize_range(None, None)

    basis, multiplier = _projection_multiplier(month_start, month_end)

    assert basis == "current_month_to_date"
    assert multiplier == 2


def test_budget_public_marks_alerting_after_threshold() -> None:
    budget = CostBudgetModel(monthly_budget_usd=100, alert_threshold_percent=75)

    public = _budget_public(budget, 80)

    assert public.usage_percent == 80
    assert public.is_alerting is True


@pytest.mark.asyncio
async def test_cost_summary_returns_totals_daily_and_budget() -> None:
    budget = CostBudgetModel(
        id=1,
        monthly_budget_usd=10,
        alert_threshold_percent=80,
    )
    session = FakeSession(
        [
            FakeResult(one_row=(1.25, 3000, 1000, 2000, 2)),
            FakeResult(
                all_rows=[
                    (
                        datetime(2026, 6, 24, tzinfo=UTC),
                        1.25,
                        3000,
                        2,
                    )
                ]
            ),
            FakeResult(scalar=budget),
        ]
    )

    response = await get_cost_summary(
        user_factory(UserRole.ADMIN),
        session,  # type: ignore[arg-type]
        datetime(2026, 6, 1, tzinfo=UTC),
        datetime(2026, 7, 1, tzinfo=UTC),
    )

    assert response.data.total_cost_usd == 1.25
    assert response.data.total_tokens == 3000
    assert response.data.request_count == 2
    assert response.data.budget.usage_percent == 12.5
    assert response.data.daily[0].request_count == 2


@pytest.mark.asyncio
async def test_list_cost_usage_returns_paginated_events() -> None:
    event = LLMUsageEventModel(
        id=3,
        user_id=7,
        operation="reasoner-decide",
        model_name="deepseek-v4-flash",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        cost_usd=0.01,
    )
    session = FakeSession([FakeResult(scalars=[event])])

    response = await list_cost_usage(
        user_factory(UserRole.ADMIN),
        session,  # type: ignore[arg-type]
        datetime(2026, 6, 1, tzinfo=UTC),
        datetime(2026, 7, 1, tzinfo=UTC),
        10,
        0,
    )

    assert response.data[0].operation == "reasoner-decide"
    assert response.meta.count == 1
    assert response.meta.limit == 10


@pytest.mark.asyncio
async def test_evaluation_metrics_returns_current_baseline_and_deltas() -> None:
    session = FakeSession(
        [
            FakeResult(one_row=(4, 1200.0, 1800.0, 0.75, 0.02, 0.08, 2)),
            FakeResult(one_row=(2, 1000.0, 1500.0, 1.0, 0.01, 0.02, 1)),
        ]
    )

    response = await get_evaluation_metrics(
        user_factory(UserRole.ADMIN),
        session,  # type: ignore[arg-type]
        datetime(2026, 6, 1, tzinfo=UTC),
        datetime(2026, 7, 1, tzinfo=UTC),
    )

    metrics = {item.key: item for item in response.data.metrics}
    assert response.data.baseline_range.start == datetime(2026, 5, 2, tzinfo=UTC)
    assert metrics["avg_latency_ms"].current_value == 1200
    assert metrics["avg_latency_ms"].baseline_value == 1000
    assert metrics["avg_latency_ms"].delta_percent == 20
    assert metrics["p95_latency_ms"].current_value == 1800
    assert metrics["success_rate"].current_value == 75
    assert metrics["avg_cost_per_run"].current_value == 0.02
    assert metrics["projected_cost_per_active_user_month"].sample_count == 4


@pytest.mark.asyncio
async def test_evaluation_metrics_returns_null_baseline_without_samples() -> None:
    session = FakeSession(
        [
            FakeResult(one_row=(1, 500.0, 500.0, 1.0, 0.03, 0.03, 1)),
            FakeResult(one_row=(0, None, None, 0, None, 0, 0)),
        ]
    )

    response = await get_evaluation_metrics(
        user_factory(UserRole.ADMIN),
        session,  # type: ignore[arg-type]
        datetime(2026, 6, 1, tzinfo=UTC),
        datetime(2026, 7, 1, tzinfo=UTC),
    )

    metrics = {item.key: item for item in response.data.metrics}
    assert metrics["avg_latency_ms"].baseline_value is None
    assert metrics["avg_latency_ms"].delta_percent is None


@pytest.mark.asyncio
async def test_user_monthly_report_groups_users_and_unknown_bucket() -> None:
    session = FakeSession(
        [
            FakeResult(
                all_rows=[
                    (
                        7,
                        "Admin",
                        "admin@example.com",
                        1.5,
                        3000,
                        4,
                        2,
                        datetime(2026, 6, 10, tzinfo=UTC),
                    ),
                    (
                        None,
                        None,
                        None,
                        0.5,
                        1000,
                        1,
                        1,
                        datetime(2026, 6, 9, tzinfo=UTC),
                    ),
                ]
            )
        ]
    )

    response = await get_user_monthly_report(
        user_factory(UserRole.ADMIN),
        session,  # type: ignore[arg-type]
        datetime(2026, 6, 1, tzinfo=UTC),
        datetime(2026, 7, 1, tzinfo=UTC),
    )

    assert response.data.users[0].user_id == 7
    assert response.data.users[0].projected_monthly_cost_usd == 1.5
    assert response.data.users[0].avg_cost_per_run_usd == 0.75
    assert response.data.users[1].user_name == "Người dùng chưa xác định"
    assert response.data.total_projected_monthly_cost_usd == 2
    assert response.data.average_projected_monthly_cost_per_user_usd == 1


@pytest.mark.asyncio
async def test_update_cost_budget_updates_existing_budget() -> None:
    budget = CostBudgetModel(id=1, monthly_budget_usd=5, alert_threshold_percent=70)
    session = FakeSession([FakeResult(scalar=budget)])

    response = await update_cost_budget(
        CostBudgetUpdateRequest(monthly_budget_usd=25, alert_threshold_percent=90),
        user_factory(UserRole.ADMIN),
        session,  # type: ignore[arg-type]
    )

    assert response.data.monthly_budget_usd == 25
    assert response.data.alert_threshold_percent == 90


def test_estimate_cost_uses_deepseek_model_pricing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agent.pricing.settings.llm_provider", "deepseek")

    pricing = resolve_model_pricing("deepseek-v4-flash")

    assert pricing is not None
    assert pricing.provider == "deepseek"
    assert pricing.input_cache_miss_usd_per_1m_tokens == 0.14
    assert pricing.input_cache_hit_usd_per_1m_tokens == 0.0028
    assert pricing.output_usd_per_1m_tokens == 0.28
    assert (
        estimate_cost_usd(
            1_000_000,
            1_000_000,
            cache_read_tokens=100_000,
            model_name="deepseek-v4-flash",
        )
        == 0.40628
    )


def test_deepseek_compatibility_alias_uses_flash_pricing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agent.pricing.settings.llm_provider", "auto")

    pricing = resolve_model_pricing("deepseek-reasoner")

    assert pricing is not None
    assert pricing.model == "deepseek-reasoner"
    assert pricing.output_usd_per_1m_tokens == 0.28


def test_unknown_model_without_registry_pricing_returns_zero_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("agent.pricing.settings.llm_provider", "deepseek")

    assert resolve_model_pricing("deepseek-unknown") is None
    assert estimate_cost_usd(1_000_000, 1_000_000, model_name="deepseek-unknown") == 0


@pytest.mark.asyncio
async def test_record_llm_usage_persists_usage_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[LLMUsageEventModel] = []

    class FakeUsageSession:
        def add(self, event: LLMUsageEventModel) -> None:
            event.id = 1
            captured.append(event)

    @asynccontextmanager
    async def fake_db_session() -> AsyncIterator[FakeUsageSession]:
        yield FakeUsageSession()

    class FakeResponse:
        usage_metadata = {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "input_token_details": {"cache_read": 10},
            "output_token_details": {"reasoning": 5},
        }
        response_metadata = {"model_name": "deepseek-test"}

    monkeypatch.setattr("agent.usage.db_session", fake_db_session)
    token = set_trace_context(
        AgentTraceContext(run_id="run-1", user_id=7, session_id="12")
    )
    try:
        await record_llm_usage(FakeResponse(), operation="reasoner-decide")
    finally:
        reset_trace_context(token)

    assert captured[0].user_id == 7
    assert captured[0].chat_session_id == 12
    assert captured[0].model_name == "deepseek-test"
    assert captured[0].cache_read_tokens == 10
    assert captured[0].reasoning_tokens == 5


@pytest.mark.asyncio
async def test_record_agent_run_metric_aggregates_usage_by_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[AgentRunMetricModel] = []

    class FakeMetricSession:
        async def execute(self, statement: Any) -> FakeResult:
            return FakeResult(one_row=(2, 350, 0.042))

        def add(self, metric: AgentRunMetricModel) -> None:
            metric.id = 1
            captured.append(metric)

    @asynccontextmanager
    async def fake_db_session() -> AsyncIterator[FakeMetricSession]:
        yield FakeMetricSession()

    monkeypatch.setattr("agent.run_metrics.db_session", fake_db_session)

    await record_agent_run_metric(
        run_id="run-1",
        user_id=7,
        session_id="12",
        duration_ms=1234.5,
        iterations=3,
        success=True,
        termination_reason="done",
        streamed=True,
    )

    assert captured[0].run_id == "run-1"
    assert captured[0].chat_session_id == 12
    assert captured[0].llm_call_count == 2
    assert captured[0].total_tokens == 350
    assert captured[0].cost_usd == 0.042
    assert captured[0].streamed is True
