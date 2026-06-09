from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError

from api.dependencies import get_auth_redis, get_current_user
from api.main import app
from core import settings
from core.security import (
    LEGACY_PASSWORD_HASH,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    seconds_until_expiry,
    verify_password,
)
from infrastructure.database.postgres import get_session
from models.user import UserModel

INVALID_JWT_SECRET = "wrong-secret-that-is-at-least-32-bytes-long"


class FakeResult:
    def __init__(self, user: UserModel | None) -> None:
        self._user = user

    def scalar_one_or_none(self) -> UserModel | None:
        return self._user


class FakeSession:
    def __init__(
        self,
        users: list[UserModel] | None = None,
        *,
        fail_on_flush: bool = False,
    ) -> None:
        self.users = users or []
        self.added_user: UserModel | None = None
        self.execute_calls = 0
        self.fail_on_flush = fail_on_flush

    async def execute(self, statement: Any) -> FakeResult:
        self.execute_calls += 1
        statement_text = str(statement)
        statement_values = {
            str(value) for value in getattr(statement.compile(), "params", {}).values()
        }
        for user in self.users:
            if user.deleted_at is not None and "deleted_at IS NULL" in statement_text:
                continue
            if (
                user.email in statement_text
                or user.email in statement_values
                or str(user.id) in statement_values
            ):
                return FakeResult(user)
        return FakeResult(None)

    def add(self, user: UserModel) -> None:
        self.added_user = user
        self.users.append(user)

    async def flush(self) -> None:
        if self.fail_on_flush:
            raise IntegrityError(
                "INSERT INTO users",
                {},
                Exception("duplicate email"),
            )
        if self.added_user is not None and self.added_user.id is None:
            self.added_user.id = 1

    async def refresh(self, user: UserModel) -> None:
        return None


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.fail = False

    async def get(self, key: str) -> str | None:
        if self.fail:
            raise RedisError("redis unavailable")
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int) -> None:
        if self.fail:
            raise RedisError("redis unavailable")
        self.values[key] = value
        self.ttls[key] = ex


def user_factory(
    *,
    user_id: int = 1,
    email: str = "user@example.com",
    password: str = "password123",
    deleted: bool = False,
    legacy: bool = False,
) -> UserModel:
    return UserModel(
        id=user_id,
        name="User",
        email=email,
        password_hash=LEGACY_PASSWORD_HASH if legacy else hash_password(password),
        deleted_at=datetime.now(UTC) if deleted else None,
    )


async def request(
    method: str,
    url: str,
    *,
    session: FakeSession | None = None,
    redis: FakeRedis | None = None,
    **kwargs: Any,
) -> Any:
    fake_session = session or FakeSession()
    fake_redis = redis or FakeRedis()

    async def override_session() -> AsyncGenerator[FakeSession, None]:
        yield fake_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_auth_redis] = lambda: fake_redis
    try:
        cookies = kwargs.pop("cookies", None)
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            if cookies is not None:
                for name, value in cookies.items():
                    client.cookies.set(name, value)
            return await client.request(method, url, **kwargs)
    finally:
        app.dependency_overrides.clear()


def test_password_hashing_does_not_store_plaintext() -> None:
    password_hash = hash_password("password123")

    assert password_hash != "password123"
    assert verify_password("password123", password_hash)
    assert not verify_password("wrong-password", password_hash)
    assert not verify_password("password123", LEGACY_PASSWORD_HASH)


def test_access_token_round_trip() -> None:
    token, expires_in = create_access_token(1)

    payload = decode_access_token(token)

    assert expires_in == 3600
    assert payload["sub"] == "1"
    assert payload["type"] == "access"
    assert "jti" in payload


def test_refresh_token_round_trip() -> None:
    token, expires_in = create_refresh_token(1)

    payload = decode_refresh_token(token)

    assert expires_in == 2_592_000
    assert payload["sub"] == "1"
    assert payload["type"] == "refresh"
    assert "jti" in payload


def test_token_expiry_uses_consistent_numeric_timestamps() -> None:
    token, expires_in = create_access_token(1)
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)
    assert payload["exp"] - payload["iat"] == expires_in


def test_seconds_until_expiry_uses_epoch_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("core.security.time", lambda: 1_000.9)

    assert seconds_until_expiry({"exp": 1_100}) == 100
    assert seconds_until_expiry({"exp": 900}) == 0


def test_decoders_reject_wrong_token_type() -> None:
    access_token, _access_expires_in = create_access_token(1)
    refresh_token, _refresh_expires_in = create_refresh_token(1)

    with pytest.raises(TokenError):
        decode_access_token(refresh_token)
    with pytest.raises(TokenError):
        decode_refresh_token(access_token)


@pytest.mark.parametrize(
    "payload_override",
    [
        {"type": "refresh"},
        {"jti": None},
        {"sub": None},
    ],
)
def test_decode_access_token_rejects_invalid_claims(
    payload_override: dict[str, str | None],
) -> None:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": "1",
        "jti": "token-id",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "type": "access",
    }
    payload.update(payload_override)
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenError):
        decode_access_token(token)


def test_decode_access_token_rejects_bad_signature() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "1",
            "jti": "token-id",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "type": "access",
        },
        INVALID_JWT_SECRET,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenError):
        decode_access_token(token)


def test_decode_access_token_rejects_missing_claim() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "1",
            "jti": "token-id",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenError):
        decode_access_token(token)


def test_decode_access_token_rejects_expired_token() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "1",
            "jti": "token-id",
            "iat": now - timedelta(minutes=10),
            "exp": now - timedelta(minutes=5),
            "type": "access",
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenError):
        decode_access_token(token)


@pytest.mark.parametrize(
    "payload_override",
    [
        {"jti": None},
        {"sub": None},
        {"exp": None},
    ],
)
def test_decode_refresh_token_rejects_invalid_claims(
    payload_override: dict[str, str | None],
) -> None:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": "1",
        "jti": "token-id",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "type": "refresh",
    }
    payload.update(payload_override)
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenError):
        decode_refresh_token(token)


def test_decode_refresh_token_rejects_bad_signature() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "1",
            "jti": "token-id",
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "type": "refresh",
        },
        INVALID_JWT_SECRET,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenError):
        decode_refresh_token(token)


def test_decode_refresh_token_rejects_missing_claim() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "1",
            "jti": "token-id",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenError):
        decode_refresh_token(token)


def test_decode_refresh_token_rejects_expired_token() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "1",
            "jti": "token-id",
            "iat": now - timedelta(minutes=10),
            "exp": now - timedelta(minutes=5),
            "type": "refresh",
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(TokenError):
        decode_refresh_token(token)


def test_get_auth_redis_returns_503_when_not_initialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_get_redis() -> None:
        raise RuntimeError("Redis has not been initialized")

    monkeypatch.setattr("api.dependencies.get_redis", fail_get_redis)

    with pytest.raises(HTTPException) as exc_info:
        get_auth_redis()

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_register_success_normalizes_email_and_hides_password_hash() -> None:
    session = FakeSession()

    response = await request(
        "POST",
        f"{settings.api_prefix}/auth/register",
        session=session,
        json={
            "name": "User",
            "email": " USER@Example.COM ",
            "password": "password123",
        },
    )

    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "User", "email": "user@example.com"}
    assert session.added_user is not None
    assert session.added_user.password_hash != "password123"


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409() -> None:
    session = FakeSession(fail_on_flush=True)

    response = await request(
        "POST",
        f"{settings.api_prefix}/auth/register",
        session=session,
        json={
            "name": "User",
            "email": "user@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 409
    assert session.execute_calls == 0


@pytest.mark.asyncio
async def test_register_validates_password_length() -> None:
    response = await request(
        "POST",
        f"{settings.api_prefix}/auth/register",
        json={"name": "User", "email": "user@example.com", "password": "short"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_json_and_oauth_form_return_valid_tokens() -> None:
    session = FakeSession([user_factory()])

    json_response = await request(
        "POST",
        f"{settings.api_prefix}/auth/login",
        session=session,
        json={"email": "user@example.com", "password": "password123"},
    )
    form_response = await request(
        "POST",
        f"{settings.api_prefix}/auth/token",
        session=session,
        data={"username": "user@example.com", "password": "password123"},
    )

    assert json_response.status_code == 200
    assert form_response.status_code == 200
    for response in (json_response, form_response):
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 3600
        assert body["refresh_expires_in"] == 2_592_000
        assert "refresh_token" not in body
        assert decode_access_token(body["access_token"])["sub"] == "1"
        set_cookie = response.headers["Set-Cookie"]
        assert "refresh_token=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "samesite=lax" in set_cookie.lower()
        assert f"Path={settings.api_prefix}/auth" in set_cookie
        refresh_cookie = response.cookies.get("refresh_token")
        assert refresh_cookie is not None
        assert decode_refresh_token(refresh_cookie)["sub"] == "1"


@pytest.mark.asyncio
async def test_refresh_rotates_refresh_token_and_returns_new_pair() -> None:
    refresh_token, _expires_in = create_refresh_token(1)
    refresh_payload = decode_refresh_token(refresh_token)
    redis = FakeRedis()

    response = await request(
        "POST",
        f"{settings.api_prefix}/auth/refresh",
        session=FakeSession([user_factory()]),
        redis=redis,
        cookies={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert "refresh_token" not in body
    assert decode_access_token(body["access_token"])["sub"] == "1"
    new_refresh_token = response.cookies.get("refresh_token")
    assert new_refresh_token is not None
    new_refresh_payload = decode_refresh_token(new_refresh_token)
    assert new_refresh_payload["sub"] == "1"
    assert new_refresh_payload["jti"] != refresh_payload["jti"]
    assert redis.values[f"auth:revoked:{refresh_payload['jti']}"] == "1"
    assert 0 < redis.ttls[f"auth:revoked:{refresh_payload['jti']}"] <= 2_592_000


@pytest.mark.asyncio
async def test_refresh_rejects_missing_cookie() -> None:
    response = await request(
        "POST",
        f"{settings.api_prefix}/auth/refresh",
        session=FakeSession([user_factory()]),
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rejects_old_token_after_rotation() -> None:
    refresh_token, _expires_in = create_refresh_token(1)
    refresh_payload = decode_refresh_token(refresh_token)
    redis = FakeRedis()

    first_response = await request(
        "POST",
        f"{settings.api_prefix}/auth/refresh",
        session=FakeSession([user_factory()]),
        redis=redis,
        cookies={"refresh_token": refresh_token},
    )
    second_response = await request(
        "POST",
        f"{settings.api_prefix}/auth/refresh",
        session=FakeSession([user_factory()]),
        redis=redis,
        cookies={"refresh_token": refresh_token},
    )

    assert first_response.status_code == 200
    assert redis.values[f"auth:revoked:{refresh_payload['jti']}"] == "1"
    assert second_response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_rejects_revoked_token() -> None:
    refresh_token, _expires_in = create_refresh_token(1)
    refresh_payload = decode_refresh_token(refresh_token)
    redis = FakeRedis()
    redis.values[f"auth:revoked:{refresh_payload['jti']}"] = "1"

    response = await request(
        "POST",
        f"{settings.api_prefix}/auth/refresh",
        session=FakeSession([user_factory()]),
        redis=redis,
        cookies={"refresh_token": refresh_token},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "session",
    [
        FakeSession([]),
        FakeSession([user_factory(deleted=True)]),
        FakeSession([user_factory(legacy=True)]),
    ],
)
async def test_refresh_rejects_missing_deleted_or_legacy_user(
    session: FakeSession,
) -> None:
    refresh_token, _expires_in = create_refresh_token(1)

    response = await request(
        "POST",
        f"{settings.api_prefix}/auth/refresh",
        session=session,
        cookies={"refresh_token": refresh_token},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_fails_closed_when_redis_unavailable() -> None:
    refresh_token, _expires_in = create_refresh_token(1)
    redis = FakeRedis()
    redis.fail = True

    response = await request(
        "POST",
        f"{settings.api_prefix}/auth/refresh",
        session=FakeSession([user_factory()]),
        redis=redis,
        cookies={"refresh_token": refresh_token},
    )

    assert response.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user",
    [None, user_factory(password="other-password"), user_factory(legacy=True)],
)
async def test_login_failures_use_same_401_response(user: UserModel | None) -> None:
    session = FakeSession([] if user is None else [user])

    response = await request(
        "POST",
        f"{settings.api_prefix}/auth/login",
        session=session,
        json={"email": "user@example.com", "password": "password123"},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_me_returns_current_user() -> None:
    token, _expires_in = create_access_token(1)

    response = await request(
        "GET",
        f"{settings.api_prefix}/auth/me",
        session=FakeSession([user_factory()]),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"id": 1, "name": "User", "email": "user@example.com"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "session",
    [FakeSession([]), FakeSession([user_factory(deleted=True)])],
)
async def test_me_rejects_missing_or_deleted_user(session: FakeSession) -> None:
    token, _expires_in = create_access_token(1)

    response = await request(
        "GET",
        f"{settings.api_prefix}/auth/me",
        session=session,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_revoked_token() -> None:
    token, _expires_in = create_access_token(1)
    payload = decode_access_token(token)
    redis = FakeRedis()
    redis.values[f"auth:revoked:{payload['jti']}"] = "1"

    response = await request(
        "GET",
        f"{settings.api_prefix}/auth/me",
        session=FakeSession([user_factory()]),
        redis=redis,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_fails_closed_when_redis_unavailable() -> None:
    token, _expires_in = create_access_token(1)
    redis = FakeRedis()
    redis.fail = True

    response = await request(
        "GET",
        f"{settings.api_prefix}/auth/me",
        session=FakeSession([user_factory()]),
        redis=redis,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_logout_revokes_token_until_expiry() -> None:
    token, _expires_in = create_access_token(1)
    payload = decode_access_token(token)
    redis = FakeRedis()

    response = await request(
        "POST",
        f"{settings.api_prefix}/auth/logout",
        redis=redis,
        headers={"Authorization": f"Bearer {token}"},
    )

    key = f"auth:revoked:{payload['jti']}"
    assert response.status_code == 204
    assert redis.values[key] == "1"
    assert 0 < redis.ttls[key] <= 3600


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token_cookie_and_clears_cookie() -> None:
    access_token, _access_expires_in = create_access_token(1)
    access_payload = decode_access_token(access_token)
    refresh_token, _refresh_expires_in = create_refresh_token(1)
    refresh_payload = decode_refresh_token(refresh_token)
    redis = FakeRedis()

    response = await request(
        "POST",
        f"{settings.api_prefix}/auth/logout",
        redis=redis,
        headers={"Authorization": f"Bearer {access_token}"},
        cookies={"refresh_token": refresh_token},
    )

    assert response.status_code == 204
    assert redis.values[f"auth:revoked:{access_payload['jti']}"] == "1"
    assert redis.values[f"auth:revoked:{refresh_payload['jti']}"] == "1"
    set_cookie = response.headers["Set-Cookie"]
    assert "refresh_token=" in set_cookie
    assert "Max-Age=0" in set_cookie
    assert f"Path={settings.api_prefix}/auth" in set_cookie


@pytest.mark.asyncio
async def test_logout_fails_closed_when_redis_unavailable() -> None:
    access_token, _expires_in = create_access_token(1)
    redis = FakeRedis()
    redis.fail = True

    response = await request(
        "POST",
        f"{settings.api_prefix}/auth/logout",
        redis=redis,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_protected_routes_require_token() -> None:
    agent_response = await request(
        "POST",
        f"{settings.api_prefix}/agent/ask",
        json={"question": "hello"},
    )

    assert agent_response.status_code == 401


@pytest.mark.asyncio
async def test_protected_routes_accept_valid_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user() -> UserModel:
        return user_factory()

    async def fake_run_agent(question: str) -> str:
        return f"answer: {question}"

    app.dependency_overrides[get_current_user] = fake_current_user
    monkeypatch.setattr("api.routes.agent_routes.run_agent", fake_run_agent)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            agent_response = await client.post(
                f"{settings.api_prefix}/agent/ask",
                json={"question": "hello"},
            )
    finally:
        app.dependency_overrides.clear()

    assert agent_response.status_code == 200
    assert agent_response.json() == {"answer": "answer: hello"}
