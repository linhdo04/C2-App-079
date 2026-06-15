# Kiến trúc AI Agent

`react.py` chứa core không phụ thuộc Gemini, database hay Tavily:

- `AgentLoop`: iteration, chống lặp, termination và run summary.
- `Reasoner`: provider-neutral planning/finalization.
- `Tool`/`ToolRegistry`: capability và input schema.
- `Executor`: validation, timeout, retry/backoff và safe observation.
- `InMemoryMemory`: recent conversation và request-local ReAct steps.

`factory.py` là composition root production. Gemini là primary reasoner;
heuristic reasoner là fallback. Registry production có `calculator`,
`document_search`, `search`, `telemetry`, `analysis`.

Mỗi run có `run_id`. Structured logs ghi iteration/tool attempt/duration,
provider fallback, termination reason và final `agent_run_summary`.

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
