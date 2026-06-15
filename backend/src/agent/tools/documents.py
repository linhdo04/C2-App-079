"""Allowlisted local document search."""

import asyncio
import os
import stat
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
                    if not resolved.is_relative_to(root) or candidate.is_symlink():
                        continue
                    relative = resolved.relative_to(root)
                    if relative.suffix.lower() not in ALLOWED_EXTENSIONS:
                        continue
                    text = _read_document(root, relative, self._max_file_bytes)
                except OSError:
                    continue
                if text is None:
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


def _read_document(root: Path, relative: Path, max_file_bytes: int) -> str | None:
    """Open each path component without following symlinks."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | nofollow | cloexec
    file_flags = os.O_RDONLY | nofollow | cloexec
    directory_fds: list[int] = []
    file_fd: int | None = None
    try:
        directory_fd = os.open(root, directory_flags)
        directory_fds.append(directory_fd)
        for part in relative.parts[:-1]:
            directory_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            directory_fds.append(directory_fd)

        file_fd = os.open(relative.name, file_flags, dir_fd=directory_fd)
        file_stat = os.fstat(file_fd)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_size > max_file_bytes:
            return None
        chunks: list[bytes] = []
        remaining = max_file_bytes + 1
        while remaining:
            chunk = os.read(file_fd, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > max_file_bytes:
            return None
        return content.decode("utf-8", errors="replace")
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for directory_fd in reversed(directory_fds):
            os.close(directory_fd)


__all__ = ["DocumentSearchInput", "DocumentSearchTool"]
