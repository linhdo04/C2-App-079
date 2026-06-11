"""Allowlisted local document search."""

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from ..react import Tool, ToolContext

ALLOWED_EXTENSIONS = {".md", ".txt", ".rst", ".csv", ".json"}


class DocumentSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=5, ge=1, le=20)


class DocumentSearchTool(Tool):
    name = "document_search"
    description = "Search configured local documentation roots."
    input_model = DocumentSearchInput

    def __init__(self, roots: list[str], *, max_file_bytes: int = 1_000_000) -> None:
        self._roots = tuple(Path(root).expanduser().resolve() for root in roots if root)
        self._max_file_bytes = max_file_bytes

    async def execute(self, tool_input: BaseModel, context: ToolContext) -> str:
        data = DocumentSearchInput.model_validate(tool_input)
        if not self._roots:
            return "Document search is not configured."
        return await asyncio.to_thread(self._search, data)

    def _search(self, data: DocumentSearchInput) -> str:
        matches: list[str] = []
        query = data.query.casefold()
        for root in self._roots:
            if not root.is_dir():
                continue
            for candidate in root.rglob("*"):
                if len(matches) >= data.max_results:
                    break
                try:
                    resolved = candidate.resolve(strict=True)
                    if (
                        not resolved.is_file()
                        or not resolved.is_relative_to(root)
                        or candidate.is_symlink()
                        or resolved.suffix.lower() not in ALLOWED_EXTENSIONS
                        or resolved.stat().st_size > self._max_file_bytes
                    ):
                        continue
                    text = resolved.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if query in resolved.name.casefold() or query in text.casefold():
                    excerpt = next(
                        (
                            line.strip()
                            for line in text.splitlines()
                            if query in line.casefold()
                        ),
                        text[:300].strip(),
                    )
                    matches.append(f"{resolved.relative_to(root)}: {excerpt[:500]}")
        return "\n".join(matches) if matches else "No matching documents."


__all__ = ["DocumentSearchInput", "DocumentSearchTool"]
