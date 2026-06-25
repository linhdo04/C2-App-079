# 0006 — Refactor AI Agent runtime to LangGraph

## Status

Accepted

## Context

The production AI Agent previously used a custom ReAct loop. The project now
needs a LangChain/LangGraph-native runtime while preserving existing API, SSE,
guardrail, tracing, retry, and tool-policy contracts.

## Decision

Use a custom LangGraph `StateGraph` for the agent runtime instead of a prebuilt
agent. Keep the existing provider-neutral `Reasoner`, `ToolPolicy`, `Executor`,
and `Tool` abstractions, but orchestrate them as graph nodes.

Use official `langgraph-checkpoint-postgres` with `AsyncPostgresSaver` for
durable runtime checkpoints. The saver owns its checkpoint tables and may run
its idempotent setup at startup when `LANGGRAPH_CHECKPOINT_SETUP_ON_START=True`.
This is a deliberate exception to the application schema rule that SQLModel
models are migrated via Alembic.

## Consequences

- Public API and frontend contracts remain unchanged.
- Chat UI persistence still uses `ChatHistoryModel`; LangGraph checkpoints are
  runtime snapshots keyed by `thread_id`.
- Agent workflow can later add branching, interrupts, or resumability without
  replacing the runtime foundation.
- Operations must ensure the app database user can create/update LangGraph
  checkpoint tables when auto setup is enabled.
