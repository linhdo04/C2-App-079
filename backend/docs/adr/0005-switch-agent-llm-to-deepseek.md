Title: Switch production agent LLM to DeepSeek
Date: 2026-06-25
Status: Accepted

Context

The application needs provider/model-aware cost tracking and the product is
moving to DeepSeek models (`deepseek-v4-flash`, `deepseek-v4-pro`,
`deepseek-chat`, `deepseek-reasoner`). The ReAct loop and tool interfaces are
already provider-neutral.

Decision

Use `langchain-deepseek` and `ChatDeepSeek` as the production LLM client. Keep
`DEFAULT_MODEL` and `LLM_PROVIDER` configuration, defaulting to DeepSeek, and
use LangChain structured output through `with_structured_output` for reasoner,
tool-policy, fallback-router, and search-filter calls.

Consequences

- Pros: runtime provider matches cost-management pricing, keeps existing ReAct
  loop/testable boundaries, and removes the previous direct runtime provider
  dependency.
- Cons: the application now depends on DeepSeek API keys, quotas, model
  availability, and structured-output behavior from `langchain-deepseek`.

Alternatives considered

- Keep the previous provider and only estimate DeepSeek pricing: rejected
  because runtime costs would not match the intended provider.
- Build a multi-provider factory now: deferred until there is a concrete need to
  switch providers at runtime.
