from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import HTTPException

from agent.pricing import estimate_cost_usd, resolve_model_pricing
from agent.tracing import AgentTraceContext, reset_trace_context, set_trace_context
from agent.usage import record_llm_usage
from api.dependencies import require_admin_user
from api.routes.admin_routes import (
    CostBudgetUpdateRequest,
    _budget_public,
    _normalize_range,
    get_cost_summary,
    list_cost_usage,
    update_cost_budget,
)
from models.llm_usage import CostBudgetModel, LLMUsageEventModel
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
