from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from core import settings, setup_logging
from infrastructure import close_db, close_redis, get_redis, init_db, init_redis

from .middlewares import error_handling, logging, rate_limiting
from .routes import agent_router


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


app = FastAPI(lifespan=lifespan)
app.add_middleware(logging.RequestLoggingMiddleware)
app.add_middleware(
    rate_limiting.RateLimitMiddleware,
    ip_limit=60,
    ip_window=60,
    key_limit=600,
    key_window=60,
)
app.add_middleware(error_handling.ErrorHandlingMiddleware, debug=settings.app_debug)

app.include_router(agent_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Hello, FastAPI with Uvicorn!"}
