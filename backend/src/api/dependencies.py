from typing import Annotated, Any, cast

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from core import settings
from core.security import (
    LEGACY_PASSWORD_HASH,
    TokenError,
    decode_access_token,
)
from infrastructure.cache.redis import get_redis
from infrastructure.database.postgres import get_session
from models.user import UserModel

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_prefix}/auth/token",
)


def auth_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def redis_unavailable_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication service unavailable",
    )


def get_auth_redis() -> Redis:
    try:
        return get_redis()
    except RuntimeError as exc:
        raise redis_unavailable_error() from exc


async def get_current_token_payload(
    token: Annotated[str, Depends(oauth2_scheme)],
    redis: Annotated[Redis, Depends(get_auth_redis)],
) -> dict[str, Any]:
    try:
        payload = decode_access_token(token)
        revoked = await redis.get(f"auth:revoked:{payload['jti']}")
    except TokenError as exc:
        raise auth_error() from exc
    except RedisError as exc:
        raise redis_unavailable_error() from exc

    if revoked is not None:
        raise auth_error()

    return payload


async def get_current_user(
    payload: Annotated[dict[str, Any], Depends(get_current_token_payload)],
    session: Annotated[AsyncSession, Depends(get_session)],
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
    if user is None or user.password_hash == LEGACY_PASSWORD_HASH:
        raise auth_error()

    return user
