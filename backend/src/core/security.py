from datetime import timedelta
from time import time
from typing import Any
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from core import settings

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
LEGACY_PASSWORD_HASH = "!legacy-user-no-password!"

_password_hash = PasswordHash.recommended()


class TokenError(Exception):
    """Raised when a JWT cannot be trusted."""


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash == LEGACY_PASSWORD_HASH:
        return False
    return _password_hash.verify(password, password_hash)


def _create_token(
    user_id: int,
    token_type: str,
    expires_delta: timedelta,
) -> tuple[str, int]:
    issued_at = int(time())
    expires_in = int(expires_delta.total_seconds())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "jti": str(uuid4()),
        "iat": issued_at,
        "exp": issued_at + expires_in,
        "type": token_type,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_in


def create_access_token(user_id: int) -> tuple[str, int]:
    return _create_token(
        user_id,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: int) -> tuple[str, int]:
    return _create_token(
        user_id,
        REFRESH_TOKEN_TYPE,
        timedelta(days=settings.refresh_token_expire_days),
    )


def _decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "jti", "iat", "exp", "type"]},
        )
    except jwt.InvalidTokenError as exc:
        raise TokenError("Invalid token") from exc

    if payload.get("type") != expected_type:
        raise TokenError("Invalid token type")
    for claim in ("sub", "jti"):
        if not isinstance(payload.get(claim), str) or not payload[claim]:
            raise TokenError(f"Invalid token {claim}")
    for claim in ("iat", "exp"):
        if not isinstance(payload.get(claim), int):
            raise TokenError(f"Invalid token {claim}")

    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    return _decode_token(token, ACCESS_TOKEN_TYPE)


def decode_refresh_token(token: str) -> dict[str, Any]:
    return _decode_token(token, REFRESH_TOKEN_TYPE)


def seconds_until_expiry(payload: dict[str, Any]) -> int:
    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise TokenError("Invalid token expiry")

    return max(0, exp - int(time()))
