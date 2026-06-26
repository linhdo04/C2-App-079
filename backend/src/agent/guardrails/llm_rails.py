"""Extension point for model-based guardrails.

LangChain's guardrails documentation describes model-based after-agent checks as
an optional layer. The production agent currently keeps only deterministic rails
for latency/cost predictability, but this module reserves a focused location for
future LLM-backed checks without changing the pipeline API.
"""
