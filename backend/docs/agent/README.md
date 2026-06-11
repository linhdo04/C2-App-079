# Production ReAct Agent

Agent trong `backend/src/agent/` dùng một vòng lặp ReAct duy nhất. LangGraph cũ
đã bị xóa. Public HTTP response và SSE envelope không thay đổi.

## Runtime

```text
goal + recent chat history
-> Gemini Reasoner
-> schema-validated Action
-> Executor
-> Observation
-> repeat or final answer
```

`Action.input` là JSON object. Mỗi tool khai báo Pydantic `input_model`;
`Executor` validate trước khi chạy, áp timeout và exponential backoff chỉ cho
tool idempotent/retryable. Tool-not-found, validation và permanent errors không
retry.

Loop chặn trùng `tool + canonical input` và ghi termination reason:
`done`, `max_iterations`, `no_progress`, hoặc `reasoner_error`.

## Production tools

- `calculator`: AST arithmetic giới hạn.
- `document_search`: chỉ đọc root trong `AGENT_DOCUMENT_ROOTS`.
- `search`: Tavily.
- `telemetry`: dữ liệu mission thuộc authenticated user.
- `analysis`: ước tính sản lượng cây trồng.

Mock file/web tools chỉ nằm trong `agent.tools.examples`, không được đăng ký
production.

## Memory và streaming

Chat routes tải tối đa `AGENT_MEMORY_MAX_MESSAGES` message gần nhất, giữ đúng
thứ tự thời gian và giới hạn tổng ký tự bằng
`AGENT_MEMORY_MAX_CHARACTERS`. `/agent/ask` không tải history.

`stream_agent()` phát safe routing/tool/synthesis status khi công việc thực sự
diễn ra, sau đó phát final answer theo nhiều token event. Thought, observation
và exception nội bộ không đi ra client. Chat chỉ được persist sau khi final
answer hoàn chỉnh.

## Cấu hình

```text
AGENT_MAX_ITERATIONS=6
AGENT_TOOL_MAX_RETRIES=1
AGENT_TOOL_RETRY_BACKOFF_SECONDS=0.25
AGENT_TOOL_TIMEOUT_SECONDS=15
AGENT_LLM_TIMEOUT_SECONDS=20
AGENT_MEMORY_MAX_MESSAGES=10
AGENT_MEMORY_MAX_CHARACTERS=12000
AGENT_DOCUMENT_ROOTS=
```

## Mở rộng

Tool mới implement `Tool`, khai báo `input_model`, `idempotent`, `retryable`,
rồi đăng ký tại `factory.py`. Provider mới implement `Reasoner.decide()` và
`Reasoner.finalize()`; không cần sửa loop.

Xem thêm [kiến trúc](architecture.md), [tools](tools.md),
[phát triển](development.md), và [Agent API](../api/agent.md).
