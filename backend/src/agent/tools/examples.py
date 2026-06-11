"""Offline mock tools for unit tests and demos only."""

from collections.abc import Mapping

from pydantic import BaseModel, Field

from ..react import Tool, ToolContext


class MockQueryInput(BaseModel):
    query: str = Field(min_length=1)


class MockFileSearchTool(Tool):
    name = "mock_file_search"
    description = "Search an in-memory filename/content mapping."
    input_model = MockQueryInput

    def __init__(self, files: Mapping[str, str] | None = None) -> None:
        self._files = dict(files or {})

    async def execute(self, tool_input: BaseModel, context: ToolContext) -> str:
        query = MockQueryInput.model_validate(tool_input).query.casefold()
        matches = [
            f"{name}: {content}"
            for name, content in self._files.items()
            if query in name.casefold() or query in content.casefold()
        ]
        return "\n".join(matches) if matches else "No matching file."


class MockWebSearchTool(Tool):
    name = "mock_web_search"
    description = "Return deterministic mock web results."
    input_model = MockQueryInput

    def __init__(self, results: Mapping[str, str] | None = None) -> None:
        self._results = dict(results or {})

    async def execute(self, tool_input: BaseModel, context: ToolContext) -> str:
        query = MockQueryInput.model_validate(tool_input).query
        return self._results.get(query, f"Mock result for: {query}")


__all__ = ["MockFileSearchTool", "MockQueryInput", "MockWebSearchTool"]
