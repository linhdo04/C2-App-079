"""Simple test script for the AI agent."""

import asyncio

import pytest

from agent import run_agent


@pytest.mark.asyncio
async def test_agent() -> None:
    """Test agent với câu hỏi mẫu."""
    question = "Cho tôi thông tin về lúa nước ở Việt Nam"
    answer = await run_agent(question)
    assert isinstance(answer, str)
    assert len(answer) > 0


if __name__ == "__main__":
    asyncio.run(test_agent())
