import uuid
from time import perf_counter
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core import set_correlation_id

_logger = structlog.get_logger("http.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        set_correlation_id(cid)

        start = perf_counter()
        response: Response | None = None
        error: BaseException | None = None

        try:
            response = await call_next(request)
        except Exception as exc:
            error = exc
            raise
        finally:
            duration_ms = round((perf_counter() - start) * 1000, 2)
            status_code = response.status_code if response else 500

            bound = _logger.bind(
                method=request.method,
                path=request.url.path,
                query=str(request.url.query) or None,
                status_code=status_code,
                duration_ms=duration_ms,
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )

            if error:
                bound.error("request_failed", exc_info=error)
            elif status_code >= 500:
                bound.error("request_server_error")
            elif status_code >= 400:
                bound.warning("request_client_error")
            else:
                bound.info("request_completed")

        if response is not None:
            response.headers["X-Correlation-ID"] = cid

        return response
