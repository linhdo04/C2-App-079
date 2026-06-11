"""Tavily search production tool."""

import asyncio
from typing import Any, cast

from pydantic import BaseModel, Field
from tavily import TavilyClient  # type: ignore[import-untyped]

from core import settings

from ..react import Tool, ToolContext


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    max_results: int = Field(default=5, ge=1, le=10)


class SearchTool(Tool):
    name = "search"
    description = "Search current agricultural information on the web."
    input_model = SearchInput
    retryable = True

    def __init__(self) -> None:
        self._client = cast(Any, TavilyClient(api_key=settings.tavily_api_key))

    async def execute(self, tool_input: BaseModel, context: ToolContext) -> str:
        data = SearchInput.model_validate(tool_input)
        results = await asyncio.to_thread(
            self._client.search,
            query=data.query,
            max_results=data.max_results,
        )
        return (
            "\n\n".join(
                f"- {item['title']}: {item['content']}"
                for item in results.get("results", [])
            )
            or "Không tìm thấy kết quả phù hợp."
        )


__all__ = ["SearchInput", "SearchTool"]
