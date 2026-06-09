Title: Use LangChain agent with Google Generative AI (Gemini)
Date: 2026-06-07
Status: Accepted

Context

Service needs an LLM-driven agent for natural-language queries and tool orchestration (web search, DB lookup, weather).

Decision

Use `langchain` agent patterns and the Google Generative AI (Gemini) model via the `langchain_google_genai` integration.

Consequences

- Pros: established agent abstractions, easy tool integration, Gemini provides high-quality generative responses.
- Cons: dependency on external API keys and quotas; must design safe tool usage and error handling.

Alternatives considered

- Directly calling LLM APIs without LangChain: more manual orchestration.
- Other providers (OpenAI, Anthropic): viable alternatives; chosen provider aligns with available keys and requirements.
