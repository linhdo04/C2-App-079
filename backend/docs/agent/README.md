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
Reasoner yêu cầu Gemini trả JSON qua native response schema và tự validate bằng
Pydantic, kèm bước phục hồi parser cho raw provider response bị bọc/lẫn text
nhưng vẫn chứa JSON hợp lệ. Nếu reasoner chính lỗi, fallback dùng Gemini router
schema nhỏ để chọn tool; nếu router cũng lỗi thì lỗi được trả về API thay vì
tự mặc định dùng `search`.

## Production tools

- `calculator`: AST arithmetic giới hạn.
- `search`: Tavily, sau đó lọc/tóm tắt kết quả bằng Gemini trước khi đưa vào
  ReAct memory. Nếu filter lỗi hoặc timeout, tool degrade về formatter thô và
  ghi chú lỗi lọc.
- `telemetry`: dữ liệu mission thuộc authenticated user; hỗ trợ lấy mẫu mới
  nhất hoặc lọc theo khoảng thời gian tương đối/explicit.
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

## Tracing

Agent tracing dùng Langfuse khi `LANGFUSE_PUBLIC_KEY` và
`LANGFUSE_SECRET_KEY` được cấu hình. Mỗi agent run tạo một trace `agent-run`;
LangChain/Gemini calls được gửi qua Langfuse callback để giữ model, token usage
và generation metadata. Chat routes truyền `chat_id` làm `session_id` để nhóm
multi-turn conversations trong Langfuse Sessions view.

Tool execution được bọc bằng span metadata cấp cao (`tool`, `iteration`,
`attempt`) nhưng không ghi raw tool observation để giảm rủi ro lộ dữ liệu nội bộ.

## Guardrails

Agent áp dụng guardrail deterministic theo các lớp trước/sau agent và quanh
tool execution:

- Input guardrail chặn prompt-injection rõ ràng và secret/API key trước khi gọi
  reasoner.
- PII guardrail redact email và mask credit card theo Luhn check trên input,
  tool observation và final output.
- Tool guardrail validate payload đã qua Pydantic, chặn secret trong tool input
  và sanitize tool output trước khi đưa lại vào ReAct memory.
- Output guardrail quét final answer lần cuối trước khi trả về HTTP/SSE.

Các guardrail không ghi raw nội dung vào log; log chỉ chứa stage, tool và lý do
chặn cấp cao. Đây là implementation nội bộ tương đương best practice middleware
của LangChain, phù hợp với ReAct loop riêng của project.

## Cấu hình

```text
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENABLED=True
AGENT_MAX_ITERATIONS=6
AGENT_TOOL_MAX_RETRIES=1
AGENT_TOOL_RETRY_BACKOFF_SECONDS=0.25
AGENT_TOOL_TIMEOUT_SECONDS=15
AGENT_LLM_TIMEOUT_SECONDS=20
AGENT_LLM_MAX_RETRIES=1
AGENT_LLM_RETRY_BACKOFF_SECONDS=0.5
AGENT_FALLBACK_ROUTER_TIMEOUT_SECONDS=6
AGENT_SEARCH_FILTER_ENABLED=True
AGENT_SEARCH_FILTER_TIMEOUT_SECONDS=8
AGENT_MEMORY_MAX_MESSAGES=10
AGENT_MEMORY_MAX_CHARACTERS=12000
AGENT_GUARDRAILS_ENABLED=True
AGENT_GUARDRAILS_REDACT_PII=True
AGENT_GUARDRAILS_BLOCK_SECRETS=True
AGENT_GUARDRAILS_BLOCK_PROMPT_INJECTION=True
```

## Mở rộng

Tool mới implement `Tool`, khai báo `input_model`, `idempotent`, `retryable`,
rồi đăng ký tại `factory.py`. Provider mới implement `Reasoner.decide()` và
`Reasoner.finalize()`; không cần sửa loop.

Xem thêm [kiến trúc](architecture.md), [luồng chạy](runtime-flows.md),
[tools](tools.md), [phát triển](development.md), và
[Agent API](../api/agent.md).
