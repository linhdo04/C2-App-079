"""Agent nodes for LangGraph workflow."""

import asyncio
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import structlog
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from core import settings

from .llm import llm
from .prompts import SYSTEM_PROMPT
from .state import AgentState
from .tools import analyze_crop_data, analyze_environment_telemetry, web_search

ToolRunner = Callable[[str, int | None], Awaitable[str]]
logger = structlog.get_logger(__name__)

TELEMETRY_KEYWORDS = (
    "thời tiết",
    "nhiệt độ",
    "nóng",
    "lạnh",
    "ẩm",
    "độ ẩm",
    "cảm biến",
    "telemetry",
    "môi trường",
)
ANALYSIS_KEYWORDS = (
    "diện tích",
    "năng suất",
    "sản lượng",
    "tấn/ha",
    "tấn trên ha",
    "yield",
    "ước tính",
    "tính",
    "thu hoạch",
    "sản xuất",
)
SEARCH_KEYWORDS = (
    "giá cả",
    "thị trường",
    "kỹ thuật",
    "sâu bệnh",
    "dịch bệnh",
    "trồng",
    "canh tác",
    "lúa",
    "cây",
    "mới nhất",
    "phân bón",
    "thuốc",
    "giống",
    "sâu",
    "bệnh",
    "nông sản",
)
AREA_KEYWORDS = ("ha", "hecta", "hectare")
YIELD_KEYWORDS = ("tấn/ha", "tấn trên ha", "tan/ha", "năng suất")
NUMBER_PATTERN = r"(\d+(?:\.\d+)?)"
KEYWORD_BOUNDARY = r"(?<![\w-]){keyword}(?![\w-])"
NUMERIC_KEYWORD_BOUNDARY = r"(?<![^\W\d_]){keyword}(?![^\W\d_])"


def _question_from_state(state: AgentState) -> str:
    question = state.get("question")
    if question:
        return question

    messages = state.get("messages", [])
    first_message = messages[0] if messages else None
    content = getattr(first_message, "content", "")
    return str(content or "")


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().replace(",", ".").split())


def _keyword_pattern(keyword: str) -> str:
    return KEYWORD_BOUNDARY.format(keyword=re.escape(keyword))


def _numeric_keyword_pattern(keyword: str) -> str:
    return NUMERIC_KEYWORD_BOUNDARY.format(keyword=re.escape(keyword))


def _has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(re.search(_keyword_pattern(keyword), text) for keyword in keywords)


def _route_intents(question: str) -> list[str]:
    ql = _normalize_text(question)
    intents: list[str] = []

    if _has_keyword(ql, TELEMETRY_KEYWORDS):
        intents.append("telemetry")

    if _has_keyword(ql, ANALYSIS_KEYWORDS):
        intents.append("analysis")

    if _has_keyword(ql, SEARCH_KEYWORDS):
        intents.append("search")

    if not intents:
        intents.append("general")

    return intents


def _extract_crop_data(question: str) -> dict[str, Any]:
    ql = _normalize_text(question)
    area = _extract_number_near_keywords(ql, AREA_KEYWORDS)
    yield_per_ha = _extract_number_near_keywords(ql, YIELD_KEYWORDS)

    crop_name = "không xác định"
    for crop in ("lúa", "cà phê", "tiêu", "ngô", "sắn", "cao su"):
        if crop in ql:
            crop_name = crop
            break

    return {
        "crop_name": crop_name,
        "area": area,
        "yield_per_ha": yield_per_ha,
        "season": "không xác định",
    }


def _extract_number_near_keywords(
    text: str,
    keywords: tuple[str, ...],
) -> float | None:
    normalized = _normalize_text(text)
    matches: list[tuple[int, float]] = []
    for keyword in keywords:
        keyword_pattern = _numeric_keyword_pattern(keyword)
        for match in re.finditer(
            rf"(?:{NUMBER_PATTERN}\s*{keyword_pattern})"
            rf"|(?:{keyword_pattern}\s*{NUMBER_PATTERN})",
            normalized,
        ):
            value = float(next(group for group in match.groups() if group is not None))
            matches.append((match.start(), value))

    if not matches:
        return None
    return min(matches, key=lambda item: item[0])[1]


async def _run_sync_tool_in_thread(tool_input: dict[str, Any]) -> str:
    result = await asyncio.to_thread(web_search.invoke, tool_input)
    return str(result)


async def _run_tool(
    name: str,
    question: str,
    user_id: int | None,
    runner: ToolRunner,
) -> tuple[str, str | None, str | None]:
    started_at = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            runner(question, user_id),
            timeout=settings.agent_tool_timeout_seconds,
        )
        return name, result, None
    except TimeoutError:
        logger.warning("agent_tool_timed_out", tool=name)
        return name, None, "timeout"
    except Exception as exc:  # pragma: no cover - exercised through graph tests
        logger.warning(
            "agent_tool_failed",
            tool=name,
            error_type=type(exc).__name__,
        )
        return name, None, "unavailable"
    finally:
        logger.info(
            "agent_tool_completed",
            tool=name,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )


async def _telemetry_runner(question: str, user_id: int | None) -> str:
    if user_id is None:
        return "Không thể truy vấn telemetry khi thiếu thông tin người dùng."
    result = await analyze_environment_telemetry.ainvoke(
        {"user_id": user_id, "limit": 50}
    )
    return str(result)


async def _search_runner(question: str, user_id: int | None = None) -> str:
    if hasattr(web_search, "ainvoke"):
        try:
            result = await web_search.ainvoke({"query": question})
            return str(result)
        except (AttributeError, NotImplementedError):
            pass
    return await _run_sync_tool_in_thread({"query": question})


async def _analysis_runner(question: str, user_id: int | None = None) -> str:
    result = await analyze_crop_data.ainvoke({"data": _extract_crop_data(question)})
    return str(result)


def _format_tool_context(
    tool_results: dict[str, str],
    tool_errors: dict[str, str],
) -> str:
    sections: list[str] = []
    if tool_results:
        sections.append("Kết quả tools:")
        sections.extend(f"- {name}: {result}" for name, result in tool_results.items())

    if tool_errors:
        sections.append("Lỗi tools:")
        sections.extend(f"- {name}: {error}" for name, error in tool_errors.items())

    return "\n".join(sections) if sections else "Không có tool nào được gọi."


def _fallback_answer(
    question: str,
    tool_results: dict[str, str],
    tool_errors: dict[str, str],
) -> str:
    if tool_results:
        result_text = "\n\n".join(
            f"Nguồn {name}:\n{result}" for name, result in tool_results.items()
        )
        if tool_errors:
            error_names = ", ".join(tool_errors)
            return (
                f"Tôi chưa thể tổng hợp bằng Gemini, nhưng có dữ liệu sau:\n\n"
                f"{result_text}\n\n"
                f"Lưu ý: một số nguồn chưa khả dụng ({error_names})."
            )
        return (
            f"Tôi chưa thể tổng hợp bằng Gemini, nhưng có dữ liệu sau:\n\n{result_text}"
        )

    if tool_errors:
        error_names = ", ".join(tool_errors)
        return (
            "Tôi chưa thể lấy đủ dữ liệu để trả lời câu hỏi này. "
            f"Các nguồn tạm thời chưa khả dụng: {error_names}."
        )

    return f"Tôi chưa có đủ dữ liệu để trả lời câu hỏi này. Câu hỏi đã nhận: {question}"


def _synthesis_messages(state: AgentState) -> list[BaseMessage]:
    question = _question_from_state(state)
    tool_context = _format_tool_context(
        dict(state.get("tool_results", {})),
        dict(state.get("tool_errors", {})),
    )
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"Câu hỏi người dùng:\n{question}\n\n"
                f"{tool_context}\n\n"
                "Hãy trả lời ngắn gọn, thực tế, bằng tiếng Việt. "
                "Nếu một nguồn dữ liệu lỗi hoặc không có dữ liệu, hãy nêu rõ hạn chế."
            )
        ),
    ]


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content or "")


async def stream_synthesize_answer(state: AgentState) -> AsyncIterator[str]:
    """Stream the final Gemini answer, with fallback before the first token."""
    question = _question_from_state(state)
    tool_results = dict(state.get("tool_results", {}))
    tool_errors = dict(state.get("tool_errors", {}))
    emitted = False

    try:
        async with asyncio.timeout(settings.agent_llm_timeout_seconds):
            async for chunk in llm.astream(_synthesis_messages(state)):
                content = _message_content_text(getattr(chunk, "content", ""))
                if content:
                    emitted = True
                    yield content
    except TimeoutError:
        logger.warning(
            "agent_llm_timed_out",
            operation="stream",
            emitted=emitted,
        )
        if emitted:
            raise
        yield _fallback_answer(question, tool_results, tool_errors)
        return
    except Exception as exc:
        logger.warning(
            "agent_llm_failed",
            operation="stream",
            error_type=type(exc).__name__,
            emitted=emitted,
        )
        if emitted:
            raise
        yield _fallback_answer(question, tool_results, tool_errors)
        return

    if not emitted:
        yield _fallback_answer(question, tool_results, tool_errors)


async def route_intent_node(state: AgentState) -> AgentState:
    """Detect which tools are useful for the original question."""
    question = _question_from_state(state)
    return {"question": question, "intents": _route_intents(question)}


async def execute_tools_node(state: AgentState) -> AgentState:
    """Run selected tools and keep their outputs separate from chat messages."""
    question = _question_from_state(state)
    user_id = state.get("user_id")
    intents = state.get("intents", ["general"])

    runners: dict[str, ToolRunner] = {
        "telemetry": _telemetry_runner,
        "search": _search_runner,
        "analysis": _analysis_runner,
    }

    tool_results: dict[str, str] = dict(state.get("tool_results", {}))
    tool_errors: dict[str, str] = dict(state.get("tool_errors", {}))
    tool_messages: list[BaseMessage] = []

    selected_tools: list[tuple[str, ToolRunner]] = []
    for intent in intents:
        runner = runners.get(intent)
        if runner is not None:
            selected_tools.append((intent, runner))

    tool_outputs = await asyncio.gather(
        *(
            _run_tool(intent, question, user_id, runner)
            for intent, runner in selected_tools
        )
    )
    for name, result, error in tool_outputs:
        if result is not None:
            tool_results[name] = result
            tool_messages.append(ToolMessage(content=result, tool_call_id=name))
        elif error is not None:
            tool_errors[name] = error

    return {
        "tool_results": tool_results,
        "tool_errors": tool_errors,
        "messages": tool_messages,
    }


async def synthesize_answer_node(state: AgentState) -> AgentState:
    """Use Gemini to produce the final answer from the original question."""
    question = _question_from_state(state)
    tool_results = dict(state.get("tool_results", {}))
    tool_errors = dict(state.get("tool_errors", {}))

    try:
        response = await asyncio.wait_for(
            llm.ainvoke(_synthesis_messages(state)),
            timeout=settings.agent_llm_timeout_seconds,
        )
        answer = _message_content_text(getattr(response, "content", ""))
    except TimeoutError:
        logger.warning("agent_llm_timed_out", operation="invoke")
        answer = _fallback_answer(question, tool_results, tool_errors)
    except Exception as exc:
        logger.warning(
            "agent_llm_failed",
            operation="invoke",
            error_type=type(exc).__name__,
        )
        answer = _fallback_answer(question, tool_results, tool_errors)

    if not answer:
        answer = _fallback_answer(question, tool_results, tool_errors)

    return {"answer": answer, "messages": [AIMessage(content=answer)]}


__all__ = [
    "execute_tools_node",
    "route_intent_node",
    "stream_synthesize_answer",
    "synthesize_answer_node",
]
