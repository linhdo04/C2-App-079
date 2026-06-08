"""Tests for the AI agent workflow."""

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agent import run_agent
from agent.graph import graph
from agent.nodes import execute_tools_node, route_intent_node, synthesize_answer_node


class FakeLLM:
    async def ainvoke(self, messages: list[Any]) -> AIMessage:
        return AIMessage(content=f"Tổng hợp: {messages[-1].content}")


@pytest.mark.asyncio
async def test_route_intent_detects_weather() -> None:
    result = await route_intent_node(
        {
            "question": "Dự báo thời tiết ở Hà Nội hôm nay",
            "messages": [HumanMessage(content="Dự báo thời tiết ở Hà Nội hôm nay")],
        }
    )

    assert result["intents"] == ["weather"]


@pytest.mark.asyncio
async def test_route_intent_detects_analysis() -> None:
    question = "Phân tích sản lượng lúa với 10 ha và năng suất 6 tấn/ha"

    result = await route_intent_node(
        {
            "question": question,
            "messages": [HumanMessage(content=question)],
        }
    )

    assert result["intents"] == ["analysis", "search"]


@pytest.mark.asyncio
async def test_execute_tools_uses_original_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_questions: list[str] = []

    async def fake_search_runner(question: str) -> str:
        seen_questions.append(question)
        return "search result"

    monkeypatch.setattr("agent.nodes._search_runner", fake_search_runner)

    result = await execute_tools_node(
        {
            "question": "Cho tôi kỹ thuật trồng lúa",
            "intents": ["search"],
            "messages": [
                HumanMessage(content="Cho tôi kỹ thuật trồng lúa"),
                AIMessage(content="previous node output"),
            ],
        }
    )

    assert seen_questions == ["Cho tôi kỹ thuật trồng lúa"]
    assert result["tool_results"] == {"search": "search result"}


@pytest.mark.asyncio
async def test_execute_tools_records_tool_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_weather_runner(question: str) -> str:
        raise RuntimeError("weather unavailable")

    monkeypatch.setattr("agent.nodes._weather_runner", failing_weather_runner)

    result = await execute_tools_node(
        {
            "question": "Dự báo thời tiết ở Đà Nẵng",
            "intents": ["weather"],
            "messages": [HumanMessage(content="Dự báo thời tiết ở Đà Nẵng")],
        }
    )

    assert result["tool_results"] == {}
    assert result["tool_errors"] == {"weather": "weather unavailable"}


@pytest.mark.asyncio
async def test_synthesize_answer_uses_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent.nodes.llm", FakeLLM())

    result = await synthesize_answer_node(
        {
            "question": "Cho tôi kỹ thuật trồng lúa",
            "messages": [HumanMessage(content="Cho tôi kỹ thuật trồng lúa")],
            "tool_results": {"search": "Kết quả search"},
            "tool_errors": {},
        }
    )

    assert "Tổng hợp:" in result["answer"]
    assert "Kết quả search" in result["answer"]


@pytest.mark.asyncio
async def test_synthesize_answer_falls_back_when_llm_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingLLM:
        async def ainvoke(self, messages: list[Any]) -> AIMessage:
            raise RuntimeError("llm unavailable")

    monkeypatch.setattr("agent.nodes.llm", FailingLLM())

    result = await synthesize_answer_node(
        {
            "question": "Cho tôi kỹ thuật trồng lúa",
            "messages": [HumanMessage(content="Cho tôi kỹ thuật trồng lúa")],
            "tool_results": {"search": "Kết quả search"},
            "tool_errors": {"weather": "timeout"},
        }
    )

    assert "Kết quả search" in result["answer"]
    assert "weather" in result["answer"]


@pytest.mark.asyncio
async def test_graph_preserves_question_and_returns_final_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_runner(question: str) -> str:
        assert question == "Cho tôi kỹ thuật trồng lúa"
        return "search result"

    monkeypatch.setattr("agent.nodes._search_runner", fake_search_runner)
    monkeypatch.setattr("agent.nodes.llm", FakeLLM())

    result = await graph.ainvoke(
        {
            "question": "Cho tôi kỹ thuật trồng lúa",
            "messages": [HumanMessage(content="Cho tôi kỹ thuật trồng lúa")],
        }
    )

    assert result["question"] == "Cho tôi kỹ thuật trồng lúa"
    assert result["tool_results"] == {"search": "search result"}
    assert "search result" in result["answer"]


@pytest.mark.asyncio
async def test_run_agent_returns_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_ainvoke(state: dict[str, Any]) -> dict[str, Any]:
        assert state["question"] == "Xin tư vấn trồng lúa"
        return {"answer": "Câu trả lời cuối"}

    monkeypatch.setattr("agent.agent.graph.ainvoke", fake_ainvoke)

    answer = await run_agent("Xin tư vấn trồng lúa")

    assert answer == "Câu trả lời cuối"
