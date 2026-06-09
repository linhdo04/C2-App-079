import pytest
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from sqlalchemy import DateTime
from starlette.middleware.errors import ServerErrorMiddleware

from api.main import app
from core.config import Settings
from models import (
    ChatHistoryModel,
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


@pytest.mark.asyncio
async def test_cors_preflight_allows_configured_frontend() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.options(
            "/auth/login",
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
            "/auth/login",
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
