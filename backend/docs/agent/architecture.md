# Kiến trúc AI Agent

Runtime production dùng custom LangGraph `StateGraph` nhưng vẫn giữ các
abstraction provider-neutral trong `react.py`:

- `AgentLoop`: build/execute LangGraph graph, iteration, chống lặp, termination
  và run summary.
- `ToolPolicy`: source-priority classifier chạy trước reasoner mỗi iteration; trả `Action | None`.
- `Reasoner`: provider-neutral planning/finalization.
- `Tool`/`ToolRegistry`: capability và input schema.
- `Executor`: validation, timeout, retry/backoff và safe observation.
- `InMemoryMemory`: recent conversation và request-local ReAct steps.

Graph topology:

```text
START
-> input_guardrail
-> plan (tool policy hoặc reasoner)
-> execute_tool
-> plan ... hoặc finalize
-> END
```

State graph lưu goal, conversation, ReAct steps, iteration, calls, final
response và termination reason. Callback/event handler không nằm trong state để
checkpoint có thể serialize an toàn.

`factory.py` là composition root production. DeepSeek là primary reasoner;
fallback reasoner dùng DeepSeek router schema nhỏ để chọn tool khi primary lỗi.
Nếu router fallback cũng lỗi, lỗi được trả về API thay vì tự chạy `search`.
Registry production có `calculator`, `search`, `telemetry`, `analysis`.

Mỗi run có `run_id`. Structured logs ghi iteration/tool attempt/duration,
provider fallback, termination reason và final `agent_run_summary`.

## LangGraph checkpointing

`agent.checkpointing` khởi tạo official `AsyncPostgresSaver` từ
`langgraph-checkpoint-postgres` trong FastAPI lifespan. Khi
`LANGGRAPH_CHECKPOINT_SETUP_ON_START=True`, saver tự setup/migrate các bảng
checkpoint của LangGraph; đây là ngoại lệ có chủ đích so với schema app do
Alembic quản lý.

`thread_id`:

- `chat:{chat_id}` cho chat endpoint để nhóm state theo conversation.
- `run:{run_id}` cho `/agent/ask` stateless.

Checkpoint là durable runtime snapshot; ChatHistory/Postgres app model vẫn là
source of truth cho UI và message persistence.

## Streaming

Loop phát internal lifecycle event trước và sau tool execution. `stream_agent`
chuyển chúng thành safe progress event, không chuyển thought hoặc observation.
Final answer được chia thành token events. Route giữ SSE framing hiện tại và
persist exchange chỉ sau khi stream hoàn tất.

## Memory

Chat route xác nhận chat thuộc authenticated user trước khi query history.
History được lấy mới nhất theo giới hạn, đảo lại chronological order và cắt
theo character budget trước khi gửi reasoner. Stateless endpoint không tạo
conversation memory.
