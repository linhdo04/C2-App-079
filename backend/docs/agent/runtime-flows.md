# Luồng chạy AI Agent

Tài liệu này mô tả luồng chạy hiện tại của production agent trong
`backend/src/agent/`. Agent dùng một LangGraph `StateGraph` chung cho mọi
trường hợp; khác biệt nằm ở entrypoint HTTP, memory, streaming/persistence và
tool được chọn.

## Luồng tổng quát

```text
HTTP request
-> xác thực user
-> tạo/nạp memory nếu là chat
-> run_agent() hoặc stream_agent()
-> LangGraph StateGraph:
   -> input guardrails
   -> tool policy/reasoner chọn action hoặc final answer
   -> executor validate input tool
   -> chạy tool nếu có
   -> sanitize observation
   -> lưu step vào graph state/checkpoint
   -> lặp lại hoặc dừng
   -> finalize nếu cần
   -> output guardrails
-> trả response hoặc stream token
-> persist chat nếu là chat endpoint
```

Production registry hiện có 4 tool:

- `calculator`: tính biểu thức số học giới hạn.
- `search`: tìm kiếm web qua Tavily, trả nội dung kèm link nguồn khi Tavily có
  URL.
- `telemetry`: đọc dữ liệu nhiệt độ/độ ẩm thuộc user đang đăng nhập.
- `analysis`: ước tính sản lượng cây trồng từ diện tích và năng suất.

`document_search` không còn nằm trong production registry. Agent không đọc file
tài liệu nội bộ từ `AGENT_DOCUMENT_ROOTS` nữa.

## Entrypoint `/agent/ask`

Endpoint này là stateless.

```text
POST /agent/ask
-> get_current_user
-> run_agent(question, user_id)
-> InMemoryMemory rỗng
-> LangGraph runtime
-> trả AgentAnswerPublic(answer)
```

Đặc điểm:

- Không nạp lịch sử chat.
- Không persist câu hỏi/câu trả lời.
- Vẫn truyền `user_id` vào tool context, nên `telemetry` vẫn chỉ đọc dữ liệu
  thuộc user hiện tại.

## Entrypoint chat non-stream

Endpoint này dùng khi gửi message trong một chat có sẵn và nhận response một
lần.

```text
POST /agent/chats/{chat_id}/messages
-> xác thực user
-> kiểm tra chat còn active và thuộc user
-> load history gần nhất theo giới hạn memory
-> run_agent(question, user_id, session_id=chat_id, history)
-> LangGraph runtime
-> persist user message + assistant message
-> cập nhật title nếu chat còn là "Cuộc trò chuyện mới"
-> trả ChatMessageResponse
```

Đặc điểm:

- History được nạp theo thứ tự thời gian sau khi lấy các message gần nhất.
- `session_id` là `chat_id`, dùng cho LangSmith metadata để nhóm multi-turn
  conversations.
- Chat chỉ được persist sau khi agent có final answer.

## Entrypoint chat stream

Endpoint này dùng SSE để gửi status và token dần về frontend.

```text
POST /agent/chats/{chat_id}/messages/stream
-> xác thực user
-> kiểm tra chat active/ownership
-> load history
-> rollback read transaction trước khi stream lâu
-> stream_agent(question, user_id, session_id=chat_id, history)
   -> emit status routing
   -> emit status tool khi tool_started
   -> emit status synthesis
   -> emit token chunks
-> ghép token thành answer
-> persist exchange
-> commit
-> emit done
```

Nếu có lỗi trong quá trình stream hoặc persist:

```text
exception
-> rollback session
-> emit SSE error { error: "stream_error" }
```

Thought, raw observation và exception nội bộ không được stream ra client.

## Reasoner selection

Production agent dùng `FallbackReasoner`:

```text
LLMReasoner.decide()
-> nếu LLM lỗi/timeout: LLMRoutedFallbackReasoner.decide()
```

LLM nhận:

- system prompt và ReAct prompt,
- user goal,
- recent conversation,
- danh sách tool + schema,
- các ReAct step trước đó.

LLM có thể:

- trả `is_done=true` với final answer,
- hoặc chọn một action với tool name và input JSON.

Nếu primary LLM reasoner lỗi, fallback router dùng một schema nhỏ để chọn
tool từ catalog. Nếu router cũng lỗi, lỗi được trả về API/SSE để user biết hệ
thống AI đang gián đoạn; agent không tự mặc định chạy `search`.

LangGraph checkpointing dùng `thread_id=chat:{chat_id}` cho chat và
`thread_id=run:{run_id}` cho `/agent/ask`. Checkpoint giúp lưu runtime state;
chat UI vẫn đọc/ghi từ `ChatHistoryModel`.

Loop cũng có guard deterministic cho telemetry: nếu telemetry đã trả “không có
dữ liệu” thì agent không được dùng `search` để thay thế dữ liệu sensor, trừ khi
user hỏi rõ nguồn bên ngoài như web/dự báo/thời tiết hiện tại. Với ngày mơ hồ
như “ngày 18” nhưng thiếu tháng/năm, agent hỏi lại thay vì tự đoán ngày.

## Case: câu hỏi tính toán

Ví dụ: `2 * (3 + 4)` hoặc câu hỏi có số nhưng không match telemetry/search/
analysis keyword trong fallback.

```text
reasoner chọn calculator
-> executor validate CalculatorInput(expression)
-> CalculatorTool parse AST expression
-> chỉ cho phép số, +, -, *, /, %, **, unary +/- và giới hạn depth/magnitude
-> observation là kết quả hoặc lỗi biểu thức không hợp lệ
-> reasoner tổng hợp final answer
```

Tool này không retry vì lỗi thường là input/permanent error.

## Case: câu hỏi cần tìm kiếm web

Ví dụ: giá nông sản, thị trường, kỹ thuật canh tác mới nhất, sâu bệnh, phân bón
hoặc giống cây.

```text
reasoner chọn search
-> executor validate SearchInput(query, max_results)
-> SearchTool gọi Tavily
-> observation gồm title, content và Link nếu result có URL
-> reasoner chỉ được dùng facts/link có trong observation
-> final answer tiếng Việt, nêu nguồn theo dữ liệu search
```

`search` là idempotent và retryable, nên executor có thể retry timeout/network/
HTTP 429 theo cấu hình `AGENT_TOOL_MAX_RETRIES` và backoff.

## Case: câu hỏi telemetry

Ví dụ: hỏi nhiệt độ, độ ẩm, cảm biến hoặc môi trường mission.

```text
reasoner chọn telemetry
-> executor validate TelemetryInput(limit)
-> TelemetryTool kiểm tra user_id trong ToolContext
-> query telemetry thuộc mission của user
-> observation gồm mission, thiết bị, thời điểm mẫu mới nhất,
   summary nhiệt độ/độ ẩm
-> reasoner tổng hợp câu trả lời
```

Nếu thiếu `user_id`, tool trả thông báo không thể truy vấn telemetry. Nếu không
có dữ liệu, tool trả thông báo không có dữ liệu nhiệt độ/độ ẩm cho user.
Observation luôn nhắc dữ liệu telemetry là lịch sử, không phải dự báo thời tiết.
Nếu user không yêu cầu nguồn ngoài, agent dừng ở thông báo thiếu dữ liệu này và
không tự tìm web để bù.

## Case: câu hỏi phân tích sản lượng

Ví dụ: `lúa 2 ha năng suất 6 tấn/ha`.

```text
reasoner chọn analysis
-> executor validate AnalysisInput(crop_name, area, yield_per_ha, season)
-> AnalysisTool kiểm tra area và yield_per_ha
-> nếu đủ dữ liệu: total = area * yield_per_ha
-> nếu thiếu dữ liệu: observation yêu cầu diện tích và năng suất hợp lệ
-> reasoner tổng hợp final answer
```

Fallback heuristic tự trích xuất crop, area và yield cơ bản từ câu hỏi. LLM
có thể tạo input chi tiết hơn nếu prompt/context đủ rõ.

## Case: câu hỏi cần nhiều tool

LLM có thể gọi nhiều tool qua nhiều iteration, mỗi iteration chỉ chọn đúng
một action.

Ví dụ câu hỏi vừa hỏi môi trường vừa hỏi khuyến nghị kỹ thuật:

```text
iteration 1: telemetry -> lấy số đo lịch sử
iteration 2: search -> tìm khuyến nghị/kỹ thuật liên quan
iteration 3: final answer -> tổng hợp từ cả hai observations
```

Loop chặn gọi lại cùng `tool + input` đã dùng. Nếu reasoner lặp lại y hệt,
termination reason là `no_progress`, sau đó agent cố finalize từ observations
đã có.

## Case: hỏi tài liệu nội bộ

Sau khi bỏ `document_search`, agent không còn local document tool.

```text
câu hỏi về "tài liệu nội bộ" hoặc "hướng dẫn nội bộ"
-> LLM chỉ thấy calculator/search/telemetry/analysis trong tool catalog
-> nếu có thể trả lời bằng context/history thì trả lời
-> nếu cần nguồn hiện hành bên ngoài thì có thể chọn search
-> nếu không có dữ liệu phù hợp thì phải nói rõ giới hạn
```

Fallback router hiện không route riêng cho tài liệu nội bộ. Nếu router không
chọn được tool hợp lệ, fallback sẽ trả lời rằng chưa đủ dữ liệu an toàn. Nếu
router lỗi, API/SSE sẽ trả thông báo lỗi thay vì chạy một tool thay thế.

## Case: tool input không hợp lệ hoặc tool không tồn tại

```text
reasoner chọn action
-> executor tìm tool trong registry
-> nếu tool không tồn tại: observation "Tool '<name>' is not available."
-> nếu input không khớp schema: observation "Input for tool '<name>' is invalid."
-> không retry
-> step vẫn được đưa vào memory
-> reasoner/finalize tạo final answer dựa trên lỗi an toàn đó
```

## Case: tool tạm lỗi

```text
tool timeout/network/OSError/HTTP 429
-> nếu tool idempotent + retryable: retry theo max_retries + backoff
-> nếu hết retry hoặc không retryable:
   observation "Tool '<name>' is temporarily unavailable."
-> reasoner/finalize trả lời với giới hạn dữ liệu
```

Hiện `search` và `telemetry` là retryable. `calculator` và `analysis` không
retry.

## Case: guardrail chặn

Guardrails chạy ở nhiều lớp:

```text
input guardrail trước reasoner
tool input guardrail trước execute
tool output guardrail sau execute
final output guardrail trước khi trả response
```

Nếu input user bị chặn:

```text
check_input blocked
-> không gọi reasoner/tool
-> termination_reason = guardrail_blocked
-> trả safe response từ guardrail
```

Nếu tool input bị chặn, executor trả observation an toàn và không chạy tool. Nếu
tool output hoặc final output bị chặn, nội dung được thay bằng safe response đã
sanitize.

## Case: reasoner lỗi hoặc hết iteration

Nếu LLM lỗi, `FallbackReasoner` gọi heuristic. Nếu cả reasoner đang dùng vẫn
lỗi trong loop:

```text
reasoner exception
-> termination_reason = reasoner_error
-> finalize nếu có thể
-> nếu finalize cũng lỗi: "Tôi chưa thể hoàn tất yêu cầu vào lúc này."
```

Nếu đạt `AGENT_MAX_ITERATIONS` trước khi có final answer:

```text
termination_reason = max_iterations
-> reasoner.finalize(goal, memory)
-> final answer phải nêu giới hạn dựa trên observations có sẵn
```

## Tracing và logging

Mỗi run có `run_id`. Khi LangSmith được cấu hình, agent tạo root run
`agent-run`; LangChain/DeepSeek calls nhận `run_name`, tags và metadata qua
RunnableConfig để LangSmith tracing ghi nhận model, token usage và generation
metadata. Tool execution tạo span metadata cấp cao như `tool`, `iteration`,
`attempt`; raw observation không được ghi vào span metadata để giảm rủi ro lộ dữ
liệu nội bộ.
