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
# KEYS[1] : Redis key (e.g. "rl:ip:127.0.0.1")
# ARGV[1] : Current timestamp in milliseconds
# ARGV[2] : Window size in milliseconds
# ARGV[3] : Maximum number of requests allowed within the window
# ARGV[4] : Unique member for ZADD (request UUID)
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


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiting với Redis backend.

    Áp dụng hai tầng giới hạn độc lập:
      - Theo IP           : giới hạn thấp hơn, chống abuse từ anonymous traffic
      - Theo API key      : giới hạn cao hơn, dành cho authenticated clients

    Nếu request có cả IP lẫn API key → cả hai tầng đều được kiểm tra,
    tầng nào bị vượt trước thì trả 429.

    Headers trả về:
      X-RateLimit-Limit      : giới hạn áp dụng
      X-RateLimit-Remaining  : số request còn lại trong window
      Retry-After            : số giây cần chờ (chỉ khi bị block)

    Args:
        redis:           Redis async client đã kết nối.
        ip_limit:        Số request tối đa theo IP mỗi window.
        ip_window:       Độ dài window theo IP (giây).
        key_limit:       Số request tối đa theo API key mỗi window.
        key_window:      Độ dài window theo API key (giây).
        api_key_header:  Tên header chứa API key.
        exclude_paths:   Các path không áp dụng rate limit.

    Example:
        # main.py
        from redis.asyncio import Redis
        from src.api.middleware import RateLimitMiddleware

        redis = Redis.from_url("redis://localhost:6379", decode_responses=True)
        app.add_middleware(
            RateLimitMiddleware,
            redis=redis,
            ip_limit=60,
            ip_window=60,
            key_limit=600,
            key_window=60,
        )
    """

    def __init__(
        self,
        app: Any,
        redis: Redis | None = None,
        ip_limit: int = 60,
        ip_window: int = 60,
        key_limit: int = 600,
        key_window: int = 60,
        api_key_header: str = "X-API-Key",
        exclude_paths: set[str] | None = None,
    ) -> None:
        super().__init__(app)
        # Accept None for redis and do lazy initialization at request time.
        self._redis = redis
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

        # Ensure we have a Redis client and the registered Lua script.
        if self._redis is None:
            try:
                from infrastructure import get_redis

                # get_redis() may raise if Redis hasn't been initialized yet.
                self._redis = get_redis()
            except Exception as exc:
                _logger_rl.warning("rate_limit_no_redis", error=str(exc))
                # Fail-open: if Redis is not available, don't block requests.
                return await call_next(request)

        if self._script is None:
            try:
                self._script = self._redis.register_script(_SLIDING_WINDOW_SCRIPT)
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
                key=f"rl:apikey:{api_key}",
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
                "retry_after_s": retry_after_s,
            },
            headers={
                "Retry-After": str(retry_after_s),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
            },
        )
