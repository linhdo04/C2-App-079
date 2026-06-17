from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

import structlog
from fastapi import APIRouter, Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from core import settings, setup_logging
from infrastructure import close_db, close_redis, get_redis, init_db, init_redis

from .dependencies import get_current_user
from .middlewares import error_handling, logging, rate_limiting
from .responses import ERROR_RESPONSES, DataResponse
from .routes import agent_router, auth_router, dashboard_router, drone_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging(level=settings.log_level, json_indent=2)
    logger_init = structlog.get_logger("init")
    await init_db()
    await init_redis()
    try:
        app.state.redis = get_redis()
    except Exception as e:
        logger_init.warning("rate_limit_no_redis", error=str(e))

    yield
    await close_db()
    await close_redis()


app = FastAPI(
    lifespan=lifespan,
    responses=ERROR_RESPONSES,
)
app.add_exception_handler(
    RequestValidationError,
    cast(Any, error_handling.validation_exception_handler),
)
app.add_exception_handler(
    StarletteHTTPException,
    cast(Any, error_handling.http_exception_handler),
)
app.add_middleware(logging.RequestLoggingMiddleware)
app.add_middleware(
    rate_limiting.RateLimitMiddleware,
    ip_limit=60,
    ip_window=60,
    key_limit=600,
    key_window=60,
    exclude_paths={
        f"{settings.api_prefix}/health",
        "/metrics",
        "/docs",
        "/openapi.json",
    },
)
app.add_middleware(error_handling.ErrorHandlingMiddleware, debug=settings.app_debug)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


api_router = APIRouter(prefix=settings.api_prefix)
api_router.include_router(auth_router)
api_router.include_router(drone_router)
api_router.include_router(
    agent_router,
    dependencies=[Depends(get_current_user)],
)
api_router.include_router(
    dashboard_router,
    dependencies=[Depends(get_current_user)],
)


class HealthStatus(BaseModel):
    status: str


@api_router.get(
    "/health",
    tags=["health"],
    response_model=DataResponse[HealthStatus],
)
def health_check() -> DataResponse[HealthStatus]:
    return DataResponse(data=HealthStatus(status="healthy"))


app.include_router(api_router)
