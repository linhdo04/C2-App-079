"""
Structured JSON logging với:
- JSON output (production-ready)
- Correlation ID qua ContextVar
- File rotation (RotatingFileHandler)
- FastAPI request logging middleware

Example usage:
    # In any module
    import structlog
    logger = structlog.get_logger(__name__)
    logger.info("event_name", key="value", count=42)
"""

import logging
import sys
import uuid
from contextvars import ContextVar

import structlog
from structlog.types import EventDict, WrappedLogger

_correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    return _correlation_id_var.get()


def set_correlation_id(value: str | None = None) -> str:
    cid = value or str(uuid.uuid4())
    _correlation_id_var.set(cid)
    return cid


def _inject_correlation_id(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    cid = get_correlation_id()
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def setup_logging(
    level: str = "INFO",
    json_indent: int | None = None,
) -> None:
    """
    Initialize application-wide logging. Call it only once during startup.

    Logs are written to stdout as JSON — suitable for collection
    by monitoring stacks (Datadog, Grafana Loki, CloudWatch, etc.).

    Args:
        level:       Log level ("DEBUG" | "INFO" | "WARNING" | "ERROR")
        json_indent: Indent cho JSON output (None = compact, 2 = pretty).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _inject_correlation_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(indent=json_indent),
        ],
        foreign_pre_chain=shared_processors,
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(console_handler)

    for noisy in ("httpx", "httpcore", "uvicorn.access", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.get_logger(__name__).info(
        "logging_configured",
        level=level,
    )
