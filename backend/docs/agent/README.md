# Production LangGraph Agent

Agent trong `backend/src/agent/` dùng custom LangGraph `StateGraph` cho runtime
AI. Public HTTP response và SSE envelope không thay đổi.

## Runtime

```text
goal + recent chat history
-> deterministic fast path / lightweight intent router
-> input guardrail
-> LangGraph StateGraph:
   -> tool policy / DeepSeek reasoner
   -> schema-validated Action
   -> executor
   -> Observation
   -> repeat, finalize, or final answer
-> output guardrail
```

`Action.input` là JSON object. Mỗi tool khai báo Pydantic `input_model`;
`Executor` validate trước khi chạy, áp timeout và exponential backoff chỉ cho
tool idempotent/retryable. Tool-not-found, validation và permanent errors không
retry.

Graph chặn trùng `tool + canonical input` và ghi termination reason:
`done`, `max_iterations`, `no_progress`, hoặc `reasoner_error`.
Reasoner yêu cầu LLM trả JSON theo structured-output schema và tự validate bằng
Pydantic, kèm bước phục hồi parser cho raw provider response bị bọc/lẫn text
nhưng vẫn chứa JSON hợp lệ. Nếu reasoner chính lỗi, fallback dùng LLM router
schema nhỏ để chọn tool; nếu router cũng lỗi thì lỗi được trả về API thay vì
tự mặc định dùng `search`.

## Production tools

- `calculator`: AST arithmetic giới hạn.
- `search`: Tavily, sau đó lọc/tóm tắt kết quả bằng DeepSeek trước khi đưa vào
  ReAct memory. Với câu hỏi xác minh, filter phải đánh giá từng mệnh đề thay vì
  coi kết quả cùng chủ đề là bằng chứng. Nếu filter lỗi hoặc timeout, tool
  degrade về formatter thô và ghi chú lỗi lọc. Nếu reasoner tổng hợp cũng lỗi,
  fallback chỉ trả danh sách nguồn và nói rõ chưa thể xác minh, không trình bày
  snippet như kết luận.
- `telemetry`: dữ liệu mission thuộc authenticated user; hỗ trợ lấy mẫu mới
  nhất hoặc lọc theo khoảng thời gian tương đối/explicit.
- `analysis`: ước tính sản lượng cây trồng.

Mock file/web tools chỉ nằm trong `agent.tools.examples`, không được đăng ký
production.

## Memory và streaming

Chat routes tải tối đa `AGENT_MEMORY_MAX_MESSAGES` message gần nhất, giữ đúng
thứ tự thời gian và giới hạn tổng ký tự bằng
`AGENT_MEMORY_MAX_CHARACTERS`. `/agent/ask` không tải history.

Trước khi vào LangGraph, facade áp dụng fast path deterministic cho các lượt
chat chắc chắn như chào/cảm ơn/ack, sau đó dùng intent router LLM schema nhỏ
để phân loại `direct_answer`, `clarify`, hoặc `full_agent`. Router không gọi
tool, không search và dùng timeout riêng; các câu cần telemetry/search/analysis
hoặc reasoning vẫn đi qua full LangGraph agent.

`stream_agent()` phát safe routing/tool/synthesis status khi công việc thực sự
diễn ra, sau đó phát final answer theo nhiều token event. Thought, observation
và exception nội bộ không đi ra client. Chat chỉ được persist sau khi final
answer hoàn chỉnh.

LangGraph checkpointing dùng `langgraph-checkpoint-postgres` khi
`AGENT_CHECKPOINTING_ENABLED=True`. `thread_id` là `chat:{chat_id}` cho chat và
`run:{run_id}` cho `/agent/ask`; ChatHistory vẫn là source of truth cho UI.
Checkpoint tables thuộc official LangGraph saver và được setup tự động khi
`LANGGRAPH_CHECKPOINT_SETUP_ON_START=True`.

## Tracing

Agent tracing dùng LangSmith khi `LANGSMITH_API_KEY` được cấu hình và
`LANGSMITH_TRACING=True`. Mỗi request tạo một root run `agent-run`, kể cả khi
được trả lời bởi deterministic pre-router hoặc intent router. Full LangGraph,
LangChain/DeepSeek calls và span thủ công dùng chung native parent context để
nằm trong cùng trace tree. Chat routes truyền `chat_id` làm `session_id` trong
metadata để nhóm multi-turn conversations.

LangSmith client ẩn toàn bộ inputs/outputs ở mọi cấp. Trace chỉ giữ metadata an
toàn như độ dài/hash input, route, stage, iteration, attempt, latency, outcome
và error type; không lưu raw prompt, history, tool payload/observation hoặc final
answer. Trace failure là best-effort và không làm agent request thất bại. Stream
bị client hủy được đóng với outcome `cancelled` và trace context luôn được reset.

Cost Management lưu local từng LLM usage event và metric tổng hợp cho mỗi full
LangGraph run (`agent_run_metrics`) theo `run_id`, gồm latency, iterations,
termination reason, success, streamed flag, tổng token và cost. Fast paths có
LangSmith trace và structured log nhưng không được thêm vào bảng metric này để
giữ nguyên semantics của dashboard hiện tại.

Tool execution được bọc bằng span metadata cấp cao (`tool`, `iteration`,
`attempt`) nhưng không ghi raw tool observation để giảm rủi ro lộ dữ liệu nội bộ.

## Decision guards và guardrails

Decision guards trước khi chạy tool được cấu hình bằng
`backend/src/agent/decision_guard_rules.json` và được evaluate bởi
`DecisionGuardPolicy`. Các rule này xử lý những trường hợp điều phối có rủi ro
như không thay thế telemetry nội bộ bằng web search khi user chưa yêu cầu nguồn
bên ngoài, hoặc yêu cầu bổ sung ngày/tháng/năm khi query telemetry còn mơ hồ.
File config cũng khai báo các điều kiện bỏ qua tool policy sau observation đã
đủ dữ liệu để reasoner tổng hợp, ví dụ sau search hoặc telemetry point-query,
nhằm tránh loop tiếp tục gọi tool khi không còn cần thu thập thêm bằng chứng.
Graph runtime chỉ gọi policy evaluator, không nhúng trực tiếp regex, tool name
hay response text vào node logic. Các message/status user-facing của agent được
cấu hình ở `backend/src/agent/agent_messages.json` và được lookup qua
`AgentMessages`.

Agent cũng áp dụng guardrail deterministic theo các lớp trước/sau agent và quanh
tool execution:

- Input guardrail chặn prompt-injection rõ ràng và secret/API key trước khi gọi
  reasoner.
- PII guardrail redact email và mask credit card theo Luhn check trên input,
  chat history, tool observation và final output.
- Tool guardrail validate payload đã qua Pydantic, chặn secret trong tool input
  và sanitize tool output trước khi đưa lại vào ReAct memory.
- Output guardrail quét final answer lần cuối trước khi trả về HTTP/SSE; với
  streaming finalize, token được buffer và sanitize trước khi emit để tránh leak
  nội dung raw qua SSE.

Các guardrail không ghi raw nội dung vào log; log chỉ chứa stage, tool và lý do
chặn cấp cao. Đây là implementation nội bộ tương đương best practice middleware
của LangChain, phù hợp với ReAct loop riêng của project. Pipeline nằm ở
`backend/src/agent/guardrails/pipeline.py`, các rail nhỏ nằm trong
`input_rails.py` và `redaction.py`, còn pattern/message được cấu hình tại
`guardrail_rules.json` để tránh nhúng regex hoặc response text trực tiếp vào
runtime logic. Pipeline cũng tính deterministic risk score theo stage, tool và
pattern rồi log metadata `agent_guardrail_risk_scored` không chứa raw content;
điểm này chỉ dùng để quan sát khi nào nên bật LLM-based guardrail, chưa gọi LLM.
`llm_rails.py` được giữ làm extension point cho guardrail model-based nếu sau
này cần thêm lớp after-agent semantic safety check.

## Cấu hình

```text
LANGSMITH_API_KEY=
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_TRACING=True
LANGSMITH_PROJECT=
LANGSMITH_WORKSPACE_ID=
DEEPSEEK_API_KEY=
DEEPSEEK_API_BASE=https://api.deepseek.com
LLM_PROVIDER=deepseek
DEFAULT_MODEL=deepseek-v4-flash
AGENT_MAX_ITERATIONS=6
AGENT_TOOL_MAX_RETRIES=1
AGENT_TOOL_RETRY_BACKOFF_SECONDS=0.25
AGENT_TOOL_TIMEOUT_SECONDS=15
AGENT_LLM_TIMEOUT_SECONDS=20
AGENT_LLM_MAX_RETRIES=1
AGENT_LLM_RETRY_BACKOFF_SECONDS=0.5
AGENT_FALLBACK_ROUTER_TIMEOUT_SECONDS=6
AGENT_INTENT_ROUTER_ENABLED=True
AGENT_INTENT_ROUTER_TIMEOUT_SECONDS=3
AGENT_INTENT_ROUTER_MIN_CONFIDENCE=0.65
AGENT_SEARCH_FILTER_ENABLED=True
AGENT_SEARCH_FILTER_TIMEOUT_SECONDS=8
AGENT_MEMORY_MAX_MESSAGES=10
AGENT_MEMORY_MAX_CHARACTERS=12000
AGENT_GUARDRAILS_ENABLED=True
AGENT_GUARDRAILS_REDACT_PII=True
AGENT_GUARDRAILS_BLOCK_SECRETS=True
AGENT_GUARDRAILS_BLOCK_PROMPT_INJECTION=True
AGENT_CHECKPOINTING_ENABLED=True
AGENT_CHECKPOINT_DURABILITY=sync
LANGGRAPH_CHECKPOINT_SETUP_ON_START=True
```

`LLM_PROVIDER=deepseek` dùng `langchain-deepseek` và `ChatDeepSeek`. Cost
Management hiện có bảng giá tự động cho DeepSeek theo model
`deepseek-v4-flash`, `deepseek-v4-pro`, `deepseek-chat`, và
`deepseek-reasoner`. Nếu model/provider chưa có trong registry thì Cost
Management vẫn ghi nhận token nhưng chi phí USD sẽ là `0` cho đến khi bổ sung
bảng giá tương ứng.

Prompt mặc định có thể được bootstrap lên LangSmith bằng:

```bash
make agent-prompts-sync
```

Script sync `system_prompt`, `react_prompt`, `tool_policy_prompt`,
`intent_router_prompt`, và `search_filter_prompt` từ local fallback hiện tại. Dùng
`make agent-prompts-sync args="--dry-run"` để kiểm tra tên prompt trước khi
push.

## Mở rộng

Tool mới implement `Tool`, khai báo `input_model`, `idempotent`, `retryable`,
rồi đăng ký tại `factory.py`. `Tool.as_langchain_tool()` cung cấp adapter
LangChain `StructuredTool` khi cần interop. Provider mới implement
`Reasoner.decide()` và `Reasoner.finalize()`; không cần sửa graph topology trừ
khi đổi workflow.

Xem thêm [kiến trúc](architecture.md), [luồng chạy](runtime-flows.md),
[tools](tools.md), [phát triển](development.md), và
[Agent API](../api/agent.md).
