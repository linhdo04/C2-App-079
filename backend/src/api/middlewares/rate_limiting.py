import hashlib
import math
import time
import uuid
from typing import Any

import structlog
from redis.asyncio import Redis
from redis.commands.core import AsyncScript
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Sliding Window Lua Script
#
# Executes atomically on Redis, ensuring there are no race conditions
# even when multiple application instances are running concurrently.
#
# Logic:
#   1. Remove entries older than the current window (ZREMRANGEBYSCORE)
#   2. Count the remaining requests within the window (ZCARD)
#   3. If quota is available:
#        - Add the new request (ZADD)
#        - Allow the request
#   4. If the quota has been exceeded:
#        - Return the required wait time (retry_after_ms)
#
# ARGV[0] : Current timestamp in milliseconds
# ARGV[1] : Window size in milliseconds
# ARGV[2] : Maximum number of requests allowed within the window
# ARGV[3] : Unique member for ZADD (request UUID)
#
# Returns: [allowed, remaining, retry_after_ms]
_SLIDING_WINDOW_SCRIPT = """
local key          = KEYS[1]
local now_ms       = tonumber(ARGV[1])
local window_ms    = tonumber(ARGV[2])
local limit        = tonumber(ARGV[3])
local member       = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now_ms - window_ms)

local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now_ms, member)
    redis.call('PEXPIRE', key, window_ms)
    return {1, limit - count - 1, 0}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after_ms = 0
    if #oldest > 0 then
        retry_after_ms = (tonumber(oldest[2]) + window_ms) - now_ms
    end
    return {0, 0, retry_after_ms}
end
"""

_logger_rl = structlog.get_logger("rate_limit")


def _hash_rate_limit_identifier(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiting with a Redis backend.

    Applies two independent layers of rate limiting:
    - By IP      : Lower limit to prevent abuse from anonymous traffic.
    - By API Key : Higher limit reserved for authenticated clients.

    If a request contains both an IP and an API key, both layers are checked.
    Whichever limit is breached first will trigger a 429 response.

    Response Headers:
    X-RateLimit-Limit     : The applied rate limit.
    X-RateLimit-Remaining : The number of remaining requests within the current window.
    Retry-After           : The number of seconds to wait (only included when blocked).

    Args:
        ip_limit:        Maximum number of requests allowed per IP window.
        ip_window:       Duration of the IP window in seconds.
        key_limit:       Maximum number of requests allowed per API key window.
        key_window:      Duration of the API key window in seconds.
        api_key_header:  The header name containing the API key.
        exclude_paths:   List of paths exempted from rate limiting.
    """

    def __init__(
        self,
        app: Any,
        ip_limit: int = 60,
        ip_window: int = 60,
        key_limit: int = 600,
        key_window: int = 60,
        api_key_header: str = "X-API-Key",
        exclude_paths: set[str] | None = None,
    ) -> None:
        super().__init__(app)
        # Accept None for redis and do lazy initialization at request time.
        self._ip_limit = ip_limit
        self._ip_window_ms = ip_window * 1000
        self._key_limit = key_limit
        self._key_window_ms = key_window * 1000
        self._api_key_header = api_key_header
        self._exclude_paths = exclude_paths or {
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
        }
        # Script will be registered lazily once a Redis client is available.
        self._script: AsyncScript | None = None

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in self._exclude_paths:
            return await call_next(request)

        redis: Redis | None = getattr(request.app.state, "redis", None)
        if redis is None:
            _logger_rl.warning("rate_limit_no_redis")
            return await call_next(request)

        if self._script is None:
            try:
                self._script = redis.register_script(_SLIDING_WINDOW_SCRIPT)
            except Exception as exc:
                _logger_rl.warning("rate_limit_register_script_failed", error=str(exc))
                return await call_next(request)

        now_ms = int(time.time() * 1000)
        req_id = str(uuid.uuid4())

        client_ip = request.client.host if request.client else "unknown"
        api_key = request.headers.get(self._api_key_header)

        # Check rate limit by IP
        ip_allowed, ip_remaining, ip_retry_ms = await self._check(
            key=f"rl:ip:{client_ip}",
            now_ms=now_ms,
            window_ms=self._ip_window_ms,
            limit=self._ip_limit,
            member=req_id,
        )

        if not ip_allowed:
            return self._too_many(
                identifier=client_ip,
                kind="ip",
                limit=self._ip_limit,
                window_ms=self._ip_window_ms,
                retry_ms=ip_retry_ms,
            )

        # Check rate limit by API key (if present)
        key_remaining: int | None = None
        if api_key:
            key_allowed, key_remaining, key_retry_ms = await self._check(
                key=f"rl:apikey:{_hash_rate_limit_identifier(api_key)}",
                now_ms=now_ms,
                window_ms=self._key_window_ms,
                limit=self._key_limit,
                member=req_id,
            )

            if not key_allowed:
                return self._too_many(
                    identifier="<api_key>",
                    kind="api_key",
                    limit=self._key_limit,
                    window_ms=self._key_window_ms,
                    retry_ms=key_retry_ms,
                )

        response = await call_next(request)

        # Return the lower remaining quota from both layers
        # to reflect the actual rate limit status.
        remaining = (
            ip_remaining if key_remaining is None else min(ip_remaining, key_remaining)
        )
        active_limit = (
            self._ip_limit
            if key_remaining is None
            else min(self._ip_limit, self._key_limit)
        )

        response.headers["X-RateLimit-Limit"] = str(active_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response

    async def _check(
        self,
        key: str,
        now_ms: int,
        window_ms: int,
        limit: int,
        member: str,
    ) -> tuple[bool, int, int]:
        """
        Gọi Lua script, trả về (allowed, remaining, retry_after_ms).
        Nếu Redis không khả dụng → cho qua (fail open) và log warning.
        """
        try:
            if self._script is None:
                return True, limit, 0

            result = await self._script(
                keys=[key],
                args=[now_ms, window_ms, limit, member],
            )
            if not result or len(result) < 3:
                _logger_rl.warning(
                    "rate_limit_invalid_script_result", key=key, result=result
                )
                return True, limit, 0

            try:
                allowed = int(result[0]) == 1
            except Exception:
                allowed = False

            remaining = int(result[1])
            retry_ms = int(result[2])
            return allowed, remaining, retry_ms
        except Exception as exc:
            _logger_rl.warning(
                "rate_limit_redis_error",
                key=key,
                error=str(exc),
            )
            # Fail open: allow requests to proceed when Redis is unavailable.
            return True, limit, 0

    def _too_many(
        self,
        identifier: str,
        kind: str,
        limit: int,
        window_ms: int,
        retry_ms: int,
    ) -> JSONResponse:
        retry_after_s = math.ceil(retry_ms / 1000)
        _logger_rl.warning(
            "rate_limit_exceeded",
            kind=kind,
            identifier=identifier,
            limit=limit,
            window_s=window_ms // 1000,
            retry_after_s=retry_after_s,
        )
        return JSONResponse(
            status_code=429,
            content={
                "error": "rate_limit_exceeded",
                "message": f"Too many requests. Retry after {retry_after_s}s.",
                "details": {
                    "retry_after_seconds": retry_after_s,
                },
            },
            headers={
                "Retry-After": str(retry_after_s),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )
