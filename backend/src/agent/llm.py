"""LLM client shared by the agent workflow."""

from langchain_google_genai import ChatGoogleGenerativeAI

from core.config import settings

llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", api_key=settings.gemini_api_key)


__all__ = ["llm"]
