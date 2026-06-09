import traceback
from typing import Any

import structlog
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from core import get_correlation_id

_logger = structlog.get_logger("error_handler")


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, debug: bool = False) -> None:
        super().__init__(app)
        self._debug = debug

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)

        except RequestValidationError as exc:
            return self._handle_validation_error(exc)

        except HTTPException as exc:
            return self._handle_http_exception(exc)

        except Exception as exc:
            return self._handle_unexpected_error(request, exc)

    def _handle_validation_error(self, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": " → ".join(str(loc) for loc in err["loc"]),
                "message": err["msg"],
                "type": err["type"],
            }
            for err in exc.errors()
        ]

        _logger.warning(
            "validation_error",
            error_count=len(errors),
            fields=[e["field"] for e in errors],
            correlation_id=get_correlation_id(),
        )

        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "message": "Request validation failed.",
                "details": errors,
            },
        )

    def _handle_http_exception(self, exc: HTTPException) -> JSONResponse:
        log = _logger.bind(
            status_code=exc.status_code,
            detail=exc.detail,
            correlation_id=get_correlation_id(),
        )

        if exc.status_code >= 500:
            log.error("http_exception_server")
        elif exc.status_code >= 400:
            log.warning("http_exception_client")

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": _status_to_error_code(exc.status_code),
                "message": exc.detail,
            },
            headers=dict(exc.headers) if exc.headers else {},
        )

    def _handle_unexpected_error(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        _logger.error(
            "unexpected_error",
            method=request.method,
            path=request.url.path,
            exc_type=type(exc).__name__,
            exc_msg=str(exc),
            correlation_id=get_correlation_id(),
            exc_info=exc,
        )

        content: dict[str, Any] = {
            "error": "internal_server_error",
            "message": "An unexpected error occurred. Please try again later.",
        }

        if self._debug:
            content["debug"] = {
                "exc_type": type(exc).__name__,
                "exc_msg": str(exc),
                "traceback": traceback.format_exc(),
            }

        return JSONResponse(status_code=500, content=content)


def _status_to_error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        408: "request_timeout",
        409: "conflict",
        410: "gone",
        422: "validation_error",
        429: "rate_limit_exceeded",
        500: "internal_server_error",
        502: "bad_gateway",
        503: "service_unavailable",
        504: "gateway_timeout",
    }.get(status_code, "error")
