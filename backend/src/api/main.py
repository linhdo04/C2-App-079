from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core import settings, setup_logging
from infrastructure import close_db, close_redis, init_db, init_redis

from .middlewares import error_handling, logging, rate_limiting


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging(level=settings.log_level, json_indent=2)
    await init_db()
    await init_redis()
    yield
    await close_db()
    await close_redis()


app = FastAPI(lifespan=lifespan)
app.add_middleware(logging.RequestLoggingMiddleware)
app.add_middleware(
    rate_limiting.RateLimitMiddleware,
    redis=None,
    ip_limit=60,
    ip_window=60,
    key_limit=600,
    key_window=60,
)
app.add_middleware(error_handling.ErrorHandlingMiddleware, debug=settings.app_debug)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Hello, FastAPI with Uvicorn!"}
