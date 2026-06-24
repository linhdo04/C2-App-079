from datetime import UTC, date, datetime, time
from typing import Annotated, Any, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent.pricing import resolve_model_pricing
from api.dependencies import require_admin_user
from api.responses import CollectionMeta, CollectionResponse, DataResponse
from infrastructure.database.postgres import get_session
from models.base import get_utc_now
from models.llm_usage import CostBudgetModel, LLMUsageEventModel
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
