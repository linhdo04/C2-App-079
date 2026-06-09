"""Agent nodes for LangGraph workflow."""

import asyncio
import re
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from .llm import llm
from .prompts import SYSTEM_PROMPT
from .state import AgentState
from .tools import (
    analyze_crop_data,
    get_weather_forecast,
    query_crop_database,
    web_search,
)

ToolRunner = Callable[[str], Awaitable[str]]

DATABASE_KEYWORDS = (
    "user",
    "users",
    "người dùng",
    "người-dùng",
    "email",
    "họ tên",
    "tên người dùng",
    "tên user",
    "name",
)
WEATHER_KEYWORDS = (
    "thời tiết",
    "dự báo",
    "mưa",
    "nhiệt độ",
    "nắng",
    "nóng",
    "lạnh",
    "ẩm",
    "khô hạn",
    "bão",
    "áp thấp",
    "weather",
    "forecast",
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

    if _has_keyword(ql, DATABASE_KEYWORDS):
        intents.append("database")

    if _has_keyword(ql, WEATHER_KEYWORDS):
        intents.append("weather")

    if _has_keyword(ql, ANALYSIS_KEYWORDS):
        intents.append("analysis")

    if _has_keyword(ql, SEARCH_KEYWORDS):
        intents.append("search")

    if not intents:
        intents.append("general")

    return intents


def _extract_location(question: str) -> str:
    ql = _normalize_text(question)
    if "hà nội" in ql or "hanoi" in ql:
        return "Hanoi"
    if "hồ chí minh" in ql or "tp.hcm" in ql or "tphcm" in ql or "saigon" in ql:
        return "Ho Chi Minh"
    return "Hanoi"


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


def _extract_number_near_keywords(text: str, keywords: tuple[str, ...]) -> float:
    normalized = _normalize_text(text)
    for keyword in keywords:
        keyword_pattern = _numeric_keyword_pattern(keyword)
        match = re.search(
            rf"(?:{NUMBER_PATTERN}\s*{keyword_pattern})"
            rf"|(?:{keyword_pattern}\s*{NUMBER_PATTERN})",
            normalized,
        )
        if match:
            return float(next(group for group in match.groups() if group is not None))
    return 0.0


async def _run_sync_tool_in_thread(tool_input: dict[str, Any]) -> str:
    result = await asyncio.to_thread(web_search.invoke, tool_input)
    return str(result)


async def _run_tool(
    name: str,
    question: str,
    runner: ToolRunner,
) -> tuple[str, str | None, str | None]:
    try:
        result = await runner(question)
        return name, result, None
    except Exception as exc:  # pragma: no cover - exercised through graph tests
        return name, None, str(exc)


async def _database_runner(question: str) -> str:
    result = await query_crop_database.ainvoke({"query": question})
    return str(result)


async def _weather_runner(question: str) -> str:
    result = await get_weather_forecast.ainvoke(
        {"location": _extract_location(question), "days": 7}
    )
    return str(result)


async def _search_runner(question: str) -> str:
    if hasattr(web_search, "ainvoke"):
        try:
            result = await web_search.ainvoke({"query": question})
            return str(result)
        except (AttributeError, NotImplementedError):
            pass
    return await _run_sync_tool_in_thread({"query": question})


async def _analysis_runner(question: str) -> str:
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


async def route_intent_node(state: AgentState) -> AgentState:
    """Detect which tools are useful for the original question."""
    question = _question_from_state(state)
    return {"question": question, "intents": _route_intents(question)}


async def execute_tools_node(state: AgentState) -> AgentState:
    """Run selected tools and keep their outputs separate from chat messages."""
    question = _question_from_state(state)
    intents = state.get("intents", ["general"])

    runners: dict[str, ToolRunner] = {
        "database": _database_runner,
        "weather": _weather_runner,
        "search": _search_runner,
        "analysis": _analysis_runner,
    }

    tool_results: dict[str, str] = dict(state.get("tool_results", {}))
    tool_errors: dict[str, str] = dict(state.get("tool_errors", {}))
    tool_messages: list[BaseMessage] = []

    for intent in intents:
        runner = runners.get(intent)
        if runner is None:
            continue

        name, result, error = await _run_tool(intent, question, runner)
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
    tool_context = _format_tool_context(tool_results, tool_errors)

    messages = [
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

    try:
        response = await llm.ainvoke(messages)
        answer = str(getattr(response, "content", "") or "")
    except Exception:
        answer = _fallback_answer(question, tool_results, tool_errors)

    if not answer:
        answer = _fallback_answer(question, tool_results, tool_errors)

    return {"answer": answer, "messages": [AIMessage(content=answer)]}


__all__ = [
    "execute_tools_node",
    "route_intent_node",
    "synthesize_answer_node",
]
