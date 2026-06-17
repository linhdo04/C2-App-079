"""Tavily search production tool."""

import asyncio
import json
from typing import Any, Literal, cast

from pydantic import BaseModel, Field
from tavily import TavilyClient  # type: ignore[import-untyped]

from core import settings

from ..react import Tool, ToolContext
from ..reasoners import _ainvoke_llm_with_retry
from ..tracing import langchain_config


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    max_results: int = Field(default=5, ge=1, le=10)


class SearchFilterInput(BaseModel):
    question: str
    results: list[dict[str, str]]


class UsableClaim(BaseModel):
    claim: str
    source_url: str


class FilteredSearchResult(BaseModel):
    title: str
    url: str
    summary: str
    usable_claims: list[UsableClaim] = Field(default_factory=list)
    relevance_reason: str


class RejectedSearchResult(BaseModel):
    title: str
    url: str
    reason: str


class SearchFilterDecision(BaseModel):
    coverage: Literal["sufficient", "partial", "insufficient"]
    relevant_results: list[FilteredSearchResult] = Field(default_factory=list)
    rejected_results: list[RejectedSearchResult] = Field(default_factory=list)


class SearchResultFilter:
    """Gemini-backed filter that only summarizes retrieved Tavily results."""

    def __init__(
        self,
        llm: Any,
        *,
        timeout_seconds: float,
        max_retries: int = 0,
        backoff_seconds: float = 0.5,
    ) -> None:
        self._structured_llm = cast(Any, llm).bind(
            response_mime_type="application/json",
            response_schema=SearchFilterDecision.model_json_schema(),
        )
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    async def filter(self, data: SearchFilterInput) -> SearchFilterDecision:
        messages = [
            {
                "role": "system",
                "content": (
                    "You filter web search results before they enter ReAct memory. "
                    "Use only the provided title, URL, and snippet. Do not answer "
                    "the user. Do not invent URLs, titles, sources, numbers, or "
                    "facts. Put short source-grounded claims in usable_claims, each "
                    "with the exact source_url from the same result. Reject results "
                    "that do not help answer the question."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question:\n{data.question}\n\n"
                    "Raw search results JSON:\n"
                    f"{json.dumps(data.results, ensure_ascii=False)}"
                ),
            },
        ]
        response = await _ainvoke_llm_with_retry(
            lambda: self._structured_llm.ainvoke(
                messages,
                config=langchain_config(
                    "search-result-filter",
                    extra_metadata={"timeout_seconds": self._timeout_seconds},
                ),
            ),
            operation="search-result-filter",
            timeout_seconds=self._timeout_seconds,
            max_retries=self._max_retries,
            backoff_seconds=self._backoff_seconds,
        )
        return _parse_filter_decision(response)


class SearchTool(Tool):
    name = "search"
    description = "Search current agricultural information on the web."
    input_model = SearchInput
    retryable = True

    def __init__(self, result_filter: SearchResultFilter | None = None) -> None:
        self._client = cast(Any, TavilyClient(api_key=settings.tavily_api_key))
        self._result_filter = result_filter
        if self._result_filter is None and settings.agent_search_filter_enabled:
            from ..llm import llm

            self._result_filter = SearchResultFilter(
                llm,
                timeout_seconds=settings.agent_search_filter_timeout_seconds,
                max_retries=settings.agent_llm_max_retries,
                backoff_seconds=settings.agent_llm_retry_backoff_seconds,
            )

    async def execute(self, tool_input: BaseModel, context: ToolContext) -> str:
        data = SearchInput.model_validate(tool_input)
        results = await asyncio.to_thread(
            self._client.search,
            query=data.query,
            max_results=data.max_results,
        )
        raw_results = _normalize_results(results.get("results", []))
        raw_observation = _format_raw_results(raw_results)
        result_filter = getattr(self, "_result_filter", None)
        if not raw_results or result_filter is None:
            return raw_observation

        try:
            decision = await result_filter.filter(
                SearchFilterInput(
                    question=data.query,
                    results=_filter_input_results(raw_results),
                )
            )
            decision = _validate_filter_decision(decision, raw_results)
        except Exception:
            return (
                f"Ghi chú: lọc kết quả thất bại; dùng kết quả thô.\n\n{raw_observation}"
            )

        return _format_filter_decision(decision)


def _normalize_results(results: Any) -> list[dict[str, str]]:
    if not isinstance(results, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "Không có tiêu đề")
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or "").strip()
        normalized.append({"title": title, "url": url, "content": content})
    return normalized


def _filter_input_results(results: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "title": result["title"],
            "url": result["url"],
            "content": _shorten(result["content"], 1_200),
        }
        for result in results[:5]
    ]


def _format_raw_results(results: list[dict[str, str]]) -> str:
    return (
        "\n\n".join(_format_search_result(item) for item in results)
        or "Không tìm thấy kết quả phù hợp."
    )


def _format_search_result(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "Không có tiêu đề")
    content = str(item.get("content") or "").strip()
    url = str(item.get("url") or "").strip()
    result = f"- Title: {title}"
    if url:
        result = f"{result}\n  URL: {url}"
    if content:
        result = f"{result}\n  Snippet: {content}"
    return result


def _parse_filter_decision(response: Any) -> SearchFilterDecision:
    if isinstance(response, SearchFilterDecision):
        return response
    if isinstance(response, dict):
        parsed = response.get("parsed")
        if parsed is not None:
            return _parse_filter_decision(parsed)
        if response.get("parsing_error") is not None and "raw" in response:
            return _parse_filter_decision(response["raw"])
        return SearchFilterDecision.model_validate(response)
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return SearchFilterDecision.model_validate_json(content)
    return SearchFilterDecision.model_validate(content)


def _validate_filter_decision(
    decision: SearchFilterDecision,
    raw_results: list[dict[str, str]],
) -> SearchFilterDecision:
    raw_by_url = {result["url"]: result for result in raw_results if result["url"]}
    relevant_results: list[FilteredSearchResult] = []
    rejected_results: list[RejectedSearchResult] = []

    for relevant in decision.relevant_results:
        raw = raw_by_url.get(relevant.url)
        if raw is None:
            continue
        claims = [
            claim
            for claim in relevant.usable_claims
            if claim.source_url == relevant.url and claim.claim.strip()
        ]
        relevant_results.append(
            FilteredSearchResult(
                title=raw["title"],
                url=relevant.url,
                summary=relevant.summary.strip(),
                usable_claims=claims,
                relevance_reason=relevant.relevance_reason.strip(),
            )
        )

    for rejected in decision.rejected_results:
        raw = raw_by_url.get(rejected.url)
        if raw is None:
            continue
        rejected_results.append(
            RejectedSearchResult(
                title=raw["title"],
                url=rejected.url,
                reason=rejected.reason.strip(),
            )
        )

    return SearchFilterDecision(
        coverage=decision.coverage,
        relevant_results=relevant_results,
        rejected_results=rejected_results,
    )


def _format_filter_decision(decision: SearchFilterDecision) -> str:
    header = (
        f"Coverage: {decision.coverage}\n"
        f"Rejected results: {len(decision.rejected_results)}"
    )
    if not decision.relevant_results:
        return (
            f"{header}\n\nKhông tìm thấy nguồn đủ phù hợp sau khi lọc kết quả tìm kiếm."
        )

    blocks = [header]
    for result in decision.relevant_results:
        claims = "; ".join(claim.claim for claim in result.usable_claims)
        snippet = result.summary
        if claims:
            snippet = f"{snippet} Claims: {claims}"
        blocks.append(
            "\n".join(
                [
                    f"- Title: {result.title}",
                    f"  URL: {result.url}",
                    f"  Snippet: {snippet}",
                    f"  Relevance: {result.relevance_reason}",
                ]
            )
        )
    return "\n\n".join(blocks)


def _shorten(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3].rstrip() + "..."


__all__ = [
    "FilteredSearchResult",
    "RejectedSearchResult",
    "SearchFilterDecision",
    "SearchFilterInput",
    "SearchInput",
    "SearchResultFilter",
    "SearchTool",
    "UsableClaim",
]
