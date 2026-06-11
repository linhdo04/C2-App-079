Title: Use a provider-neutral ReAct loop with Gemini
Date: 2026-06-07
Status: Accepted

Context

Service needs an LLM-driven agent for natural-language queries and tool orchestration (web search, DB lookup, weather).

Decision

Use the application's explicit ReAct loop and provider-neutral `Reasoner`
interface. Gemini remains the production provider through
`langchain_google_genai`; LangGraph is not part of the runtime.

Consequences

- Pros: explicit termination, retry, schema validation, streaming, and testable
  provider/tool boundaries.
- Cons: the application owns orchestration behavior and remains dependent on
  Gemini API keys and quotas.

Alternatives considered

- Directly calling LLM APIs without LangChain: more manual orchestration.
- Other providers (OpenAI, Anthropic): viable alternatives; chosen provider aligns with available keys and requirements.
