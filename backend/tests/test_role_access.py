import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_current_user, require_operator_user
from api.main import app
from core import settings
from models.user import UserModel, UserRole


def user_factory(role: UserRole = UserRole.OPERATOR) -> UserModel:
    return UserModel(
        id=7,
        name="Role User",
        email="role-user@example.com",
        password_hash="hash",
        role=role,
    )


@pytest.mark.asyncio
async def test_require_operator_user_rejects_admin() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_operator_user(user_factory(UserRole.ADMIN))

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_operator_user_accepts_operator() -> None:
    user = user_factory(UserRole.OPERATOR)

    assert await require_operator_user(user) is user


@pytest.mark.asyncio
async def test_admin_cannot_call_dashboard_api() -> None:
    async def fake_current_user() -> UserModel:
        return user_factory(UserRole.ADMIN)

    app.dependency_overrides[get_current_user] = fake_current_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(f"{settings.api_prefix}/dashboard/telemetry")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["message"] == "Operator access required"


@pytest.mark.asyncio
async def test_operator_cannot_call_admin_api() -> None:
    async def fake_current_user() -> UserModel:
        return user_factory(UserRole.OPERATOR)

    app.dependency_overrides[get_current_user] = fake_current_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get(
                f"{settings.api_prefix}/admin/cost-management/summary"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["message"] == "Admin access required"
