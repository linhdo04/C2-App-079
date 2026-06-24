"""LLM client shared by the agent workflow."""

from langchain_deepseek import ChatDeepSeek
from pydantic import SecretStr

from core.config import settings

llm = ChatDeepSeek(
    model=settings.default_model,
    api_key=SecretStr(settings.deepseek_api_key or "missing-deepseek-api-key"),
    base_url=settings.deepseek_api_base,
)


__all__ = ["llm"]
