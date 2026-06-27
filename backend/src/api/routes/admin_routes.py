from datetime import UTC, date, datetime, time
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.pricing import resolve_model_pricing
from api.dependencies import require_admin_user
from api.responses import CollectionMeta, CollectionResponse, DataResponse
from infrastructure.database.postgres import get_session
from models.base import get_utc_now
from models.llm_usage import AgentRunMetricModel, CostBudgetModel, LLMUsageEventModel
from models.user import UserModel

router = APIRouter(prefix="/admin/cost-management", tags=["admin"])
LOCAL_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


class DateRange(BaseModel):
    start: datetime
    end: datetime


class CostBudgetPublic(BaseModel):
    monthly_budget_usd: float
    alert_threshold_percent: int
    spent_usd: float = 0
    usage_percent: float = 0
    is_alerting: bool = False


class DailyCostPublic(BaseModel):
    date: date
    cost_usd: float
    total_tokens: int
    request_count: int


class CostSummaryPublic(BaseModel):
    range: DateRange
    total_cost_usd: float
    total_tokens: int
    input_tokens: int
    output_tokens: int
    request_count: int
    budget: CostBudgetPublic
    pricing_configured: bool
    pricing_provider: str | None
    pricing_model: str | None
    pricing_source: str | None
    daily: list[DailyCostPublic]


class CostUsageEventPublic(BaseModel):
    id: int
    occurred_at: datetime
    user_id: int | None
    chat_session_id: int | None
    run_id: str | None
    operation: str
    model_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float


class CostUsageMeta(CollectionMeta):
    limit: int
    offset: int


class CostUsageResponse(CollectionResponse[CostUsageEventPublic]):
    meta: CostUsageMeta


class CostBudgetUpdateRequest(BaseModel):
    monthly_budget_usd: float = Field(ge=0)
    alert_threshold_percent: int = Field(ge=1, le=100)


class EvaluationMetricPublic(BaseModel):
    key: str
    label: str
    unit: str
    direction: str
    current_value: float | None
    baseline_value: float | None
    delta_value: float | None
    delta_percent: float | None
    sample_count: int


class EvaluationMetricsPublic(BaseModel):
    range: DateRange
    baseline_range: DateRange
    metrics: list[EvaluationMetricPublic]


class UserMonthlyCostReportItemPublic(BaseModel):
    user_id: int | None
    user_name: str
    user_email: str | None
    actual_cost_usd: float
    projected_monthly_cost_usd: float
    total_tokens: int
    llm_calls: int
    agent_runs: int
    avg_cost_per_run_usd: float | None
    last_used_at: datetime


class UserMonthlyCostReportPublic(BaseModel):
    range: DateRange
    projection_basis: str
    projection_multiplier: float
    total_projected_monthly_cost_usd: float
    average_projected_monthly_cost_per_user_usd: float
    users: list[UserMonthlyCostReportItemPublic]


def _month_range() -> tuple[datetime, datetime]:
    current = get_utc_now().astimezone(LOCAL_TIMEZONE)
    start = datetime.combine(
        current.date().replace(day=1),
        time.min,
        tzinfo=LOCAL_TIMEZONE,
    )
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    return start.astimezone(UTC), next_month.astimezone(UTC)


def _normalize_range(
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime, datetime]:
    default_start, default_end = _month_range()
    normalized_start = start or default_start
    normalized_end = end or default_end
    if normalized_start.tzinfo is None:
        normalized_start = normalized_start.replace(tzinfo=LOCAL_TIMEZONE)
    if normalized_end.tzinfo is None:
        normalized_end = normalized_end.replace(tzinfo=LOCAL_TIMEZONE)
    range_start = normalized_start.astimezone(UTC)
    range_end = normalized_end.astimezone(UTC)
    if range_start >= range_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cost date range",
        )
    return range_start, range_end


def _baseline_range(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    duration = end - start
    return start - duration, start


def _days_in_month(value: datetime) -> int:
    local_value = value.astimezone(LOCAL_TIMEZONE)
    if local_value.month == 12:
        next_month = local_value.replace(year=local_value.year + 1, month=1, day=1)
    else:
        next_month = local_value.replace(month=local_value.month + 1, day=1)
    month_start = local_value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (next_month - month_start).days


def _projection_multiplier(start: datetime, end: datetime) -> tuple[str, float]:
    now = get_utc_now()
    month_start, month_end = _month_range()
    if start == month_start and end == month_end:
        elapsed_seconds = max((min(now, month_end) - month_start).total_seconds(), 1)
        elapsed_days = elapsed_seconds / 86_400
        return "current_month_to_date", round(_days_in_month(start) / elapsed_days, 6)

    range_days = max((end - start).total_seconds() / 86_400, 1 / 86_400)
    return "normalized_30_day_range", round(30 / range_days, 6)


def _delta(
    current: float | None, baseline: float | None
) -> tuple[float | None, float | None]:
    if current is None or baseline is None:
        return None, None
    delta_value = current - baseline
    if baseline == 0:
        return delta_value, None
    return delta_value, round((delta_value / baseline) * 100, 2)


def _metric(
    *,
    key: str,
    label: str,
    unit: str,
    direction: str,
    current_value: float | None,
    baseline_value: float | None,
    sample_count: int,
) -> EvaluationMetricPublic:
    delta_value, delta_percent = _delta(current_value, baseline_value)
    return EvaluationMetricPublic(
        key=key,
        label=label,
        unit=unit,
        direction=direction,
        current_value=current_value,
        baseline_value=baseline_value,
        delta_value=delta_value,
        delta_percent=delta_percent,
        sample_count=sample_count,
    )


def _active_usage_range_statement(start: datetime, end: datetime) -> Any:
    active_clause = cast(
        ColumnElement[bool],
        cast(Any, LLMUsageEventModel.deleted_at).is_(None),
    )
    return (
        select(LLMUsageEventModel)
        .where(
            active_clause,
            cast(ColumnElement[bool], LLMUsageEventModel.occurred_at >= start),
            cast(ColumnElement[bool], LLMUsageEventModel.occurred_at < end),
        )
        .order_by(cast(Any, LLMUsageEventModel.occurred_at).desc())
    )


def _active_run_clause() -> ColumnElement[bool]:
    return cast(
        ColumnElement[bool],
        cast(Any, AgentRunMetricModel.deleted_at).is_(None),
    )


async def _run_aggregate(
    session: AsyncSession,
    start: datetime,
    end: datetime,
) -> dict[str, float | int | None]:
    active_clause = _active_run_clause()
    result = await session.execute(
        select(
            func.count(cast(Any, AgentRunMetricModel.id)),
            func.avg(cast(Any, AgentRunMetricModel.duration_ms)),
            func.percentile_cont(0.95).within_group(
                cast(Any, AgentRunMetricModel.duration_ms)
            ),
            func.coalesce(
                func.avg(
                    case(
                        (cast(Any, AgentRunMetricModel.success).is_(True), 1.0),
                        else_=0.0,
                    )
                ),
                0,
            ),
            func.avg(cast(Any, AgentRunMetricModel.cost_usd)),
            func.coalesce(func.sum(cast(Any, AgentRunMetricModel.cost_usd)), 0),
            func.count(distinct(cast(Any, AgentRunMetricModel.user_id))),
        ).where(
            active_clause,
            cast(ColumnElement[bool], AgentRunMetricModel.occurred_at >= start),
            cast(ColumnElement[bool], AgentRunMetricModel.occurred_at < end),
        )
    )
    count, avg_latency, p95_latency, success_ratio, avg_cost, total_cost, users = (
        result.one()
    )
    sample_count = int(count)
    _, multiplier = _projection_multiplier(start, end)
    active_users = int(users) or (1 if sample_count > 0 else 0)
    projected_cost_per_user = (
        float(total_cost) * multiplier / active_users if active_users > 0 else None
    )
    return {
        "sample_count": sample_count,
        "avg_latency_ms": round(float(avg_latency), 2)
        if avg_latency is not None
        else None,
        "p95_latency_ms": round(float(p95_latency), 2)
        if p95_latency is not None
        else None,
        "success_rate": round(float(success_ratio) * 100, 2)
        if sample_count > 0
        else None,
        "avg_cost_per_run": round(float(avg_cost), 6) if avg_cost is not None else None,
        "projected_cost_per_active_user_month": (
            round(projected_cost_per_user, 6)
            if projected_cost_per_user is not None
            else None
        ),
    }


async def _get_budget(session: AsyncSession) -> CostBudgetModel:
    active_clause = cast(
        ColumnElement[bool],
        cast(Any, CostBudgetModel.deleted_at).is_(None),
    )
    result = await session.execute(
        select(CostBudgetModel)
        .where(active_clause)
        .order_by(cast(Any, CostBudgetModel.id).asc())
        .limit(1)
    )
    budget = result.scalar_one_or_none()
    if budget is not None:
        return budget

    budget = CostBudgetModel()
    session.add(budget)
    await session.flush()
    await session.refresh(budget)
    return budget


def _budget_public(budget: CostBudgetModel, spent_usd: float) -> CostBudgetPublic:
    usage_percent = (
        round((spent_usd / budget.monthly_budget_usd) * 100, 2)
        if budget.monthly_budget_usd > 0
        else 0
    )
    return CostBudgetPublic(
        monthly_budget_usd=budget.monthly_budget_usd,
        alert_threshold_percent=budget.alert_threshold_percent,
        spent_usd=spent_usd,
        usage_percent=usage_percent,
        is_alerting=(
            budget.monthly_budget_usd > 0
            and usage_percent >= budget.alert_threshold_percent
        ),
    )


@router.get("/summary", response_model=DataResponse[CostSummaryPublic])
async def get_cost_summary(
    _: Annotated[UserModel, Depends(require_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> DataResponse[CostSummaryPublic]:
    range_start, range_end = _normalize_range(start, end)
    active_clause = cast(
        ColumnElement[bool],
        cast(Any, LLMUsageEventModel.deleted_at).is_(None),
    )
    totals_result = await session.execute(
        select(
            func.coalesce(func.sum(LLMUsageEventModel.cost_usd), 0),
            func.coalesce(func.sum(LLMUsageEventModel.total_tokens), 0),
            func.coalesce(func.sum(LLMUsageEventModel.input_tokens), 0),
            func.coalesce(func.sum(LLMUsageEventModel.output_tokens), 0),
            func.count(cast(Any, LLMUsageEventModel.id)),
        ).where(
            active_clause,
            cast(ColumnElement[bool], LLMUsageEventModel.occurred_at >= range_start),
            cast(ColumnElement[bool], LLMUsageEventModel.occurred_at < range_end),
        )
    )
    total_cost, total_tokens, input_tokens, output_tokens, request_count = (
        totals_result.one()
    )

    day_bucket = func.date_trunc("day", LLMUsageEventModel.occurred_at)
    daily_result = await session.execute(
        select(
            day_bucket,
            func.coalesce(func.sum(LLMUsageEventModel.cost_usd), 0),
            func.coalesce(func.sum(LLMUsageEventModel.total_tokens), 0),
            func.count(cast(Any, LLMUsageEventModel.id)),
        )
        .where(
            active_clause,
            cast(ColumnElement[bool], LLMUsageEventModel.occurred_at >= range_start),
            cast(ColumnElement[bool], LLMUsageEventModel.occurred_at < range_end),
        )
        .group_by(day_bucket)
        .order_by(day_bucket.asc())
    )
    daily = [
        DailyCostPublic(
            date=bucket.astimezone(LOCAL_TIMEZONE).date()
            if isinstance(bucket, datetime)
            else bucket,
            cost_usd=float(cost),
            total_tokens=int(tokens),
            request_count=int(count),
        )
        for bucket, cost, tokens, count in daily_result.all()
    ]
    budget = await _get_budget(session)
    pricing = resolve_model_pricing()
    return DataResponse(
        data=CostSummaryPublic(
            range=DateRange(start=range_start, end=range_end),
            total_cost_usd=float(total_cost),
            total_tokens=int(total_tokens),
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            request_count=int(request_count),
            budget=_budget_public(budget, float(total_cost)),
            pricing_configured=pricing is not None,
            pricing_provider=pricing.provider if pricing is not None else None,
            pricing_model=pricing.model if pricing is not None else None,
            pricing_source=pricing.source if pricing is not None else None,
            daily=daily,
        )
    )


@router.get("/usage", response_model=CostUsageResponse)
async def list_cost_usage(
    _: Annotated[UserModel, Depends(require_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CostUsageResponse:
    range_start, range_end = _normalize_range(start, end)
    statement = _active_usage_range_statement(range_start, range_end)
    result = await session.execute(statement.limit(limit).offset(offset))
    events = [
        CostUsageEventPublic(
            id=cast(int, event.id),
            occurred_at=event.occurred_at,
            user_id=event.user_id,
            chat_session_id=event.chat_session_id,
            run_id=event.run_id,
            operation=event.operation,
            model_name=event.model_name,
            input_tokens=event.input_tokens,
            output_tokens=event.output_tokens,
            total_tokens=event.total_tokens,
            cost_usd=event.cost_usd,
        )
        for event in result.scalars().all()
    ]
    return CostUsageResponse(
        data=events,
        meta=CostUsageMeta(count=len(events), limit=limit, offset=offset),
    )


@router.get("/evaluation-metrics", response_model=DataResponse[EvaluationMetricsPublic])
async def get_evaluation_metrics(
    _: Annotated[UserModel, Depends(require_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> DataResponse[EvaluationMetricsPublic]:
    range_start, range_end = _normalize_range(start, end)
    baseline_start, baseline_end = _baseline_range(range_start, range_end)
    current = await _run_aggregate(session, range_start, range_end)
    baseline = await _run_aggregate(session, baseline_start, baseline_end)
    sample_count = int(current["sample_count"] or 0)
    return DataResponse(
        data=EvaluationMetricsPublic(
            range=DateRange(start=range_start, end=range_end),
            baseline_range=DateRange(start=baseline_start, end=baseline_end),
            metrics=[
                _metric(
                    key="avg_latency_ms",
                    label="Latency trung bình",
                    unit="ms",
                    direction="lower_better",
                    current_value=cast(float | None, current["avg_latency_ms"]),
                    baseline_value=cast(float | None, baseline["avg_latency_ms"]),
                    sample_count=sample_count,
                ),
                _metric(
                    key="p95_latency_ms",
                    label="P95 latency",
                    unit="ms",
                    direction="lower_better",
                    current_value=cast(float | None, current["p95_latency_ms"]),
                    baseline_value=cast(float | None, baseline["p95_latency_ms"]),
                    sample_count=sample_count,
                ),
                _metric(
                    key="success_rate",
                    label="Tỷ lệ thành công",
                    unit="percent",
                    direction="higher_better",
                    current_value=cast(float | None, current["success_rate"]),
                    baseline_value=cast(float | None, baseline["success_rate"]),
                    sample_count=sample_count,
                ),
                _metric(
                    key="avg_cost_per_run",
                    label="Chi phí trung bình / run",
                    unit="usd",
                    direction="lower_better",
                    current_value=cast(float | None, current["avg_cost_per_run"]),
                    baseline_value=cast(float | None, baseline["avg_cost_per_run"]),
                    sample_count=sample_count,
                ),
                _metric(
                    key="projected_cost_per_active_user_month",
                    label="Ước tính chi phí / active user / tháng",
                    unit="usd_per_user_month",
                    direction="lower_better",
                    current_value=cast(
                        float | None,
                        current["projected_cost_per_active_user_month"],
                    ),
                    baseline_value=cast(
                        float | None,
                        baseline["projected_cost_per_active_user_month"],
                    ),
                    sample_count=sample_count,
                ),
            ],
        )
    )


@router.get(
    "/user-monthly-report",
    response_model=DataResponse[UserMonthlyCostReportPublic],
)
async def get_user_monthly_report(
    _: Annotated[UserModel, Depends(require_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> DataResponse[UserMonthlyCostReportPublic]:
    range_start, range_end = _normalize_range(start, end)
    projection_basis, multiplier = _projection_multiplier(range_start, range_end)
    active_clause = _active_run_clause()
    result = await session.execute(
        select(
            cast(Any, AgentRunMetricModel.user_id),
            cast(Any, UserModel.name),
            cast(Any, UserModel.email),
            func.coalesce(func.sum(cast(Any, AgentRunMetricModel.cost_usd)), 0),
            func.coalesce(func.sum(cast(Any, AgentRunMetricModel.total_tokens)), 0),
            func.coalesce(func.sum(cast(Any, AgentRunMetricModel.llm_call_count)), 0),
            func.count(cast(Any, AgentRunMetricModel.id)),
            func.max(cast(Any, AgentRunMetricModel.occurred_at)),
        )
        .outerjoin(UserModel, cast(Any, AgentRunMetricModel.user_id) == UserModel.id)
        .where(
            active_clause,
            cast(ColumnElement[bool], AgentRunMetricModel.occurred_at >= range_start),
            cast(ColumnElement[bool], AgentRunMetricModel.occurred_at < range_end),
        )
        .group_by(
            cast(Any, AgentRunMetricModel.user_id),
            cast(Any, UserModel.name),
            cast(Any, UserModel.email),
        )
        .order_by(
            func.coalesce(func.sum(cast(Any, AgentRunMetricModel.cost_usd)), 0).desc()
        )
    )
    users: list[UserMonthlyCostReportItemPublic] = []
    for (
        user_id,
        user_name,
        user_email,
        cost,
        tokens,
        llm_calls,
        runs,
        last_used_at,
    ) in result.all():
        actual_cost = float(cost)
        agent_runs = int(runs)
        users.append(
            UserMonthlyCostReportItemPublic(
                user_id=user_id,
                user_name=user_name or "Người dùng chưa xác định",
                user_email=user_email,
                actual_cost_usd=round(actual_cost, 6),
                projected_monthly_cost_usd=round(actual_cost * multiplier, 6),
                total_tokens=int(tokens),
                llm_calls=int(llm_calls),
                agent_runs=agent_runs,
                avg_cost_per_run_usd=(
                    round(actual_cost / agent_runs, 6) if agent_runs > 0 else None
                ),
                last_used_at=last_used_at,
            )
        )
    total_projected = round(sum(item.projected_monthly_cost_usd for item in users), 6)
    average_projected = round(total_projected / len(users), 6) if users else 0
    return DataResponse(
        data=UserMonthlyCostReportPublic(
            range=DateRange(start=range_start, end=range_end),
            projection_basis=projection_basis,
            projection_multiplier=multiplier,
            total_projected_monthly_cost_usd=total_projected,
            average_projected_monthly_cost_per_user_usd=average_projected,
            users=users,
        )
    )


@router.get("/budget", response_model=DataResponse[CostBudgetPublic])
async def get_cost_budget(
    _: Annotated[UserModel, Depends(require_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataResponse[CostBudgetPublic]:
    budget = await _get_budget(session)
    return DataResponse(data=_budget_public(budget, 0))


@router.put("/budget", response_model=DataResponse[CostBudgetPublic])
async def update_cost_budget(
    req: CostBudgetUpdateRequest,
    _: Annotated[UserModel, Depends(require_admin_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataResponse[CostBudgetPublic]:
    budget = await _get_budget(session)
    budget.monthly_budget_usd = req.monthly_budget_usd
    budget.alert_threshold_percent = req.alert_threshold_percent
    session.add(budget)
    await session.flush()
    await session.refresh(budget)
    return DataResponse(data=_budget_public(budget, 0))
