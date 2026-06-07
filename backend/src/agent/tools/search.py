from typing import Any, cast

from langchain_core.tools import tool
from tavily import TavilyClient  # type: ignore[import-untyped]

from core import settings

# Tavily client doesn't include type stubs in this repo; cast to `Any`
tavily_client = cast(Any, TavilyClient(api_key=settings.tavily_api_key))


@tool
def web_search(query: str) -> str:
    """Tìm kiếm thông tin nông nghiệp: giá cả, kỹ thuật, dịch bệnh cây trồng."""
    results = tavily_client.search(query=query, max_results=5)
    # Flatten kết quả thành string cho LLM dễ đọc
    return "\n\n".join(f"- {r['title']}: {r['content']}" for r in results["results"])
