"""
Structured JSON logging với:
- JSON output (production-ready)
- Correlation ID qua ContextVar
- File rotation (RotatingFileHandler)
- FastAPI request logging middleware
- LangGraph callback handler (graph / node / llm / tool / retriever)

Example usage:
    # In any module
    import structlog
    logger = structlog.get_logger(__name__)
    logger.info("event_name", key="value", count=42)
"""

import logging
import sys
import uuid
from collections.abc import Sequence
from contextvars import ContextVar
from time import perf_counter
from typing import Any

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


# LangGraph callback handler
#
# LangGraph executes each node as a chain and distinguishes graph/node
# events using tags and metadata stored in kwargs.
#
# The run_id / parent_run_id hierarchy can be used to reconstruct
# the execution tree:
#
#     graph (root) -> node_A -> llm_call
#                  -> node_B -> tool_call -> ...
#
# _NODE_TAG and _GRAPH_TAG are tags automatically attached by LangGraph
# to kwargs["tags"].
_NODE_TAG = "langsmith:hidden"  # Internal LangGraph tag for node wrappers
_GRAPH_TAG = "graph"


# Extract the node name from run_name (LangGraph sets run_name to the node name).
def _extract_node_name(kwargs: dict[str, Any]) -> str | None:
    return kwargs.get("run_name") or None


# LangGraph
# from src.core.logging import make_langgraph_logging_handler

# LoggingHandler = make_langgraph_logging_handler()
# result = await compiled_graph.ainvoke(
#     {"query": "..."},
#     config={"callbacks": [LoggingHandler()]},
# )


def make_langgraph_logging_handler() -> Any:
    """
    Return a LangGraph callback handler class.

    The handler distinguishes three levels of events:
        1. Graph      - the entire graph execution lifecycle
        2. Node       - individual nodes within the graph
        3. LLM / Tool / Retriever - operations executed inside a node

    Uses lazy imports so that langgraph/langchain are not required when
    this module is used standalone.

    Example:
        from src.core.logging import make_langgraph_logging_handler

        LoggingHandler = make_langgraph_logging_handler()

        # Attach the handler when invoking the graph
        app = graph.compile()
        result = await app.ainvoke(
            {"query": "..."},
            config={"callbacks": [LoggingHandler()]},
        )
    """
    from langchain_core.callbacks.base import BaseCallbackHandler
    from langchain_core.outputs import LLMResult

    _logger = structlog.get_logger("langgraph")

    class LangGraphLoggingHandler(BaseCallbackHandler):
        """
        Log the entire LangGraph execution flow as structured JSON.

        Each log record includes:
            - correlation_id  (automatically injected from ContextVar)
            - run_id          (UUID of the current execution)
            - parent_run_id   (UUID of the parent run, used to trace the execution tree)
            - node            (name of the currently executing node, if applicable)
        """

        def __init__(self) -> None:
            super().__init__()
            # Lưu thời điểm bắt đầu theo run_id để tính duration
            self._start_times: dict[str, float] = {}

        def _run_id(self, kwargs: Any) -> str:
            return str(kwargs.get("run_id", ""))

        def _parent_run_id(self, kwargs: Any) -> str | None:
            pid = kwargs.get("parent_run_id")
            return str(pid) if pid else None

        def _elapsed_ms(self, run_id: str) -> float | None:
            t = self._start_times.pop(run_id, None)
            return round((perf_counter() - t) * 1000, 2) if t is not None else None

        # Graph root chain
        # The entire LangGraph execution is represented as a root chain
        # (parent_run_id = None), with nodes as child chains.

        def on_chain_start(
            self,
            serialized: dict[str, Any],
            inputs: dict[str, Any],
            **kwargs: Any,
        ) -> None:
            run_id = self._run_id(kwargs)
            self._start_times[run_id] = perf_counter()

            node = _extract_node_name(kwargs)
            parent = self._parent_run_id(kwargs)

            if parent is None:
                # This is the graph root
                _logger.info(
                    "graph_start",
                    graph=serialized.get("id", ["unknown"])[-1],
                    input_keys=list(inputs.keys()),
                    run_id=run_id,
                )
            else:
                # This is a node inside the graph
                _logger.info(
                    "node_start",
                    node=node,
                    input_keys=list(inputs.keys()),
                    run_id=run_id,
                    parent_run_id=parent,
                )

        def on_chain_end(
            self,
            outputs: dict[str, Any],
            **kwargs: Any,
        ) -> None:
            run_id = self._run_id(kwargs)
            duration_ms = self._elapsed_ms(run_id)
            parent = self._parent_run_id(kwargs)
            node = _extract_node_name(kwargs)

            if parent is None:
                _logger.info(
                    "graph_end",
                    output_keys=list(outputs.keys()),
                    duration_ms=duration_ms,
                    run_id=run_id,
                )
            else:
                _logger.info(
                    "node_end",
                    node=node,
                    output_keys=list(outputs.keys()),
                    duration_ms=duration_ms,
                    run_id=run_id,
                    parent_run_id=parent,
                )

        def on_chain_error(
            self,
            error: BaseException,
            **kwargs: Any,
        ) -> None:
            run_id = self._run_id(kwargs)
            node = _extract_node_name(kwargs)
            parent = self._parent_run_id(kwargs)
            self._start_times.pop(run_id, None)

            _logger.error(
                "graph_error" if parent is None else "node_error",
                node=node,
                error=str(error),
                run_id=run_id,
                parent_run_id=parent,
                exc_info=error,
            )

        # LLM

        def on_llm_start(
            self,
            serialized: dict[str, Any],
            prompts: list[str],
            **kwargs: Any,
        ) -> None:
            run_id = self._run_id(kwargs)
            self._start_times[run_id] = perf_counter()
            _logger.info(
                "llm_start",
                model=serialized.get("id", ["unknown"])[-1],
                prompt_count=len(prompts),
                run_id=run_id,
                parent_run_id=self._parent_run_id(kwargs),
            )

        def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
            run_id = self._run_id(kwargs)
            duration_ms = self._elapsed_ms(run_id)
            usage: dict[str, Any] = {}
            if response.llm_output:
                usage = response.llm_output.get("token_usage", {})
            _logger.info(
                "llm_end",
                generation_count=sum(len(g) for g in response.generations),
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
                duration_ms=duration_ms,
                run_id=run_id,
                parent_run_id=self._parent_run_id(kwargs),
            )

        def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
            run_id = self._run_id(kwargs)
            self._start_times.pop(run_id, None)
            _logger.error(
                "llm_error",
                error=str(error),
                run_id=run_id,
                parent_run_id=self._parent_run_id(kwargs),
                exc_info=error,
            )

        # Tool

        def on_tool_start(
            self,
            serialized: dict[str, Any],
            input_str: str,
            **kwargs: Any,
        ) -> None:
            run_id = self._run_id(kwargs)
            self._start_times[run_id] = perf_counter()
            _logger.info(
                "tool_start",
                tool=serialized.get("name", "unknown"),
                input_preview=input_str[:300],
                run_id=run_id,
                parent_run_id=self._parent_run_id(kwargs),
            )

        def on_tool_end(self, output: str, **kwargs: Any) -> None:
            run_id = self._run_id(kwargs)
            _logger.info(
                "tool_end",
                output_preview=str(output)[:300],
                duration_ms=self._elapsed_ms(run_id),
                run_id=run_id,
                parent_run_id=self._parent_run_id(kwargs),
            )

        def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
            run_id = self._run_id(kwargs)
            self._start_times.pop(run_id, None)
            _logger.error(
                "tool_error",
                error=str(error),
                run_id=run_id,
                parent_run_id=self._parent_run_id(kwargs),
                exc_info=error,
            )

        # Retriever (RAG node)

        def on_retriever_start(
            self,
            serialized: dict[str, Any],
            query: str,
            **kwargs: Any,
        ) -> None:
            run_id = self._run_id(kwargs)
            self._start_times[run_id] = perf_counter()
            _logger.info(
                "retriever_start",
                retriever=serialized.get("id", ["unknown"])[-1],
                query_preview=query[:300],
                run_id=run_id,
                parent_run_id=self._parent_run_id(kwargs),
            )

        def on_retriever_end(
            self,
            documents: Sequence[Any],
            *,
            run_id: Any,
            parent_run_id: Any | None = None,
            **kwargs: Any,
        ) -> Any:
            rid = str(run_id) if run_id else self._run_id(kwargs)
            parent = (
                str(parent_run_id) if parent_run_id else self._parent_run_id(kwargs)
            )
            _logger.info(
                "retriever_end",
                doc_count=len(documents),
                duration_ms=self._elapsed_ms(rid),
                run_id=rid,
                parent_run_id=parent,
            )

        def on_retriever_error(self, error: BaseException, **kwargs: Any) -> None:
            run_id = self._run_id(kwargs)
            self._start_times.pop(run_id, None)
            _logger.error(
                "retriever_error",
                error=str(error),
                run_id=run_id,
                parent_run_id=self._parent_run_id(kwargs),
                exc_info=error,
            )

    return LangGraphLoggingHandler
