import pytest
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from sqlalchemy import DateTime
from starlette.middleware.errors import ServerErrorMiddleware

from api.main import app
from core import settings
from core.config import Settings
from models import (
    ChatHistoryModel,
    ChatSessionModel,
    IoTNodeModel,
    MissionModel,
    ReportModel,
    TelemetryModel,
    UserModel,
)


def test_cors_is_the_outermost_middleware() -> None:
    middleware_stack = app.build_middleware_stack()

    assert isinstance(middleware_stack, ServerErrorMiddleware)
    assert isinstance(middleware_stack.app, CORSMiddleware)


def test_api_prefix_is_applied_to_application_routes() -> None:
    route_paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert f"{settings.api_prefix}/auth/login" in route_paths
    assert f"{settings.api_prefix}/agent/ask" in route_paths
    assert f"{settings.api_prefix}/health" in route_paths
    assert f"{settings.api_prefix}/" not in route_paths
    assert "/auth/login" not in route_paths
    assert "/agent/ask" not in route_paths


@pytest.mark.asyncio
async def test_health_check_is_public() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"{settings.api_prefix}/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
    assert "x-ratelimit-limit" not in response.headers


@pytest.mark.asyncio
async def test_api_root_is_not_exposed() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(f"{settings.api_prefix}/")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cors_preflight_allows_configured_frontend() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.options(
            f"{settings.api_prefix}/auth/login",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ("http://localhost:3000")
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "POST" in response.headers["access-control-allow-methods"]


@pytest.mark.asyncio
async def test_cors_preflight_rejects_unconfigured_frontend() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.options(
            f"{settings.api_prefix}/auth/login",
            headers={
                "Origin": "http://localhost:3030",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_frontend_origins_support_multiple_values_and_trailing_slashes() -> None:
    settings = Settings(
        FRONTEND_ORIGIN=("http://localhost:3000/, https://app.example.com/ ")
    )  # type: ignore[call-arg]

    assert settings.frontend_origins == [
        "http://localhost:3000",
        "https://app.example.com",
    ]


@pytest.mark.parametrize(
    ("model", "column_names"),
    [
        (UserModel, ("created_at", "updated_at", "deleted_at")),
        (MissionModel, ("started_at", "ended_at")),
        (ChatHistoryModel, ("timestamp",)),
        (ChatSessionModel, ("created_at", "updated_at", "deleted_at")),
        (IoTNodeModel, ("last_seen",)),
        (ReportModel, ("published_at",)),
        (TelemetryModel, ("timestamp",)),
    ],
)
def test_datetime_columns_are_timezone_aware(
    model: type[object],
    column_names: tuple[str, ...],
) -> None:
    table = model.__table__  # type: ignore[attr-defined]

    for column_name in column_names:
        column_type = table.columns[column_name].type
        assert isinstance(column_type, DateTime)
        assert column_type.timezone is True
