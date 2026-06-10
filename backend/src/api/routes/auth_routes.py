from typing import Annotated, Any, cast

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import ColumnElement, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import (
    auth_error,
    get_auth_redis,
    get_current_token_payload,
    get_current_user,
    redis_unavailable_error,
)
from api.responses import DataResponse
from core import settings
from core.security import (
    LEGACY_PASSWORD_HASH,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    seconds_until_expiry,
    verify_password,
)
from infrastructure.database.postgres import get_session
from models.user import UserModel

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = f"{settings.api_prefix}/auth"


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def _get_user_by_email(
    session: AsyncSession,
    email: str,
) -> UserModel | None:
    result = await session.execute(
        select(UserModel).where(
            cast(ColumnElement[bool], UserModel.email == email),
            cast(ColumnElement[bool], cast(Any, UserModel.deleted_at).is_(None)),
        )
    )
    return result.scalar_one_or_none()


async def _authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
) -> UserModel:
    user = await _get_user_by_email(session, normalize_email(email))
    if (
        user is None
        or user.password_hash == LEGACY_PASSWORD_HASH
        or not verify_password(password, user.password_hash)
    ):
        raise auth_error()
    return user


def _set_refresh_cookie(
    response: Response,
    refresh_token: str,
    max_age: int,
) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        secure=settings.app_env == "production",
        httponly=True,
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=settings.app_env == "production",
        httponly=True,
        samesite="lax",
    )


def _token_response(user_id: int, response: Response) -> TokenResponse:
    access_token, expires_in = create_access_token(user_id)
    refresh_token, refresh_expires_in = create_refresh_token(user_id)
    _set_refresh_cookie(response, refresh_token, refresh_expires_in)
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        refresh_expires_in=refresh_expires_in,
    )


async def _revoke_token(
    redis: Redis,
    payload: dict[str, Any],
) -> None:
    ttl = seconds_until_expiry(payload)
    if ttl <= 0:
        raise auth_error()

    await redis.set(f"auth:revoked:{payload['jti']}", "1", ex=ttl)


async def _get_active_refresh_payload(
    token: str,
    redis: Redis,
) -> dict[str, Any]:
    try:
        payload = decode_refresh_token(token)
        revoked = await redis.get(f"auth:revoked:{payload['jti']}")
    except TokenError as exc:
        raise auth_error() from exc
    except RedisError as exc:
        raise redis_unavailable_error() from exc

    if revoked is not None:
        raise auth_error()

    return payload


async def _get_refresh_user(
    payload: dict[str, Any],
    session: AsyncSession,
) -> UserModel:
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise auth_error() from exc

    result = await session.execute(
        select(UserModel).where(
            cast(ColumnElement[bool], UserModel.id == user_id),
            cast(ColumnElement[bool], cast(Any, UserModel.deleted_at).is_(None)),
        )
    )
    user = result.scalar_one_or_none()
    if user is None or user.id is None or user.password_hash == LEGACY_PASSWORD_HASH:
        raise auth_error()

    return user


@router.post(
    "/register",
    response_model=DataResponse[UserPublic],
    status_code=status.HTTP_201_CREATED,
)
async def register(
    req: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataResponse[UserPublic]:
    email = normalize_email(str(req.email))
    user = UserModel(
        name=req.name.strip(),
        email=email,
        password_hash=hash_password(req.password),
    )
    session.add(user)
    try:
        await session.flush()
        await session.refresh(user)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc

    return DataResponse(data=UserPublic.model_validate(user))


@router.post("/login", response_model=DataResponse[TokenResponse])
async def login(
    req: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataResponse[TokenResponse]:
    user = await _authenticate_user(session, str(req.email), req.password)
    if user.id is None:
        raise auth_error()
    return DataResponse(data=_token_response(user.id, response))


@router.post("/token", response_model=TokenResponse)
async def token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TokenResponse:
    user = await _authenticate_user(session, form.username, form.password)
    if user.id is None:
        raise auth_error()
    return _token_response(user.id, response)


@router.post("/refresh", response_model=DataResponse[TokenResponse])
async def refresh(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_auth_redis)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> DataResponse[TokenResponse]:
    if refresh_token is None:
        raise auth_error()

    payload = await _get_active_refresh_payload(refresh_token, redis)
    user = await _get_refresh_user(payload, session)

    try:
        await _revoke_token(redis, payload)
    except RedisError as exc:
        raise redis_unavailable_error() from exc

    if user.id is None:
        raise auth_error()
    return DataResponse(data=_token_response(user.id, response))


@router.get("/me", response_model=DataResponse[UserPublic])
async def me(
    current_user: Annotated[UserModel, Depends(get_current_user)],
) -> DataResponse[UserPublic]:
    return DataResponse(data=UserPublic.model_validate(current_user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: Annotated[dict[str, object], Depends(get_current_token_payload)],
    response: Response,
    redis: Annotated[Redis, Depends(get_auth_redis)],
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)] = None,
) -> Response:
    try:
        await _revoke_token(redis, payload)
        if refresh_token is not None:
            refresh_payload = await _get_active_refresh_payload(refresh_token, redis)
            await _revoke_token(redis, refresh_payload)
    except RedisError as exc:
        raise redis_unavailable_error() from exc

    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
