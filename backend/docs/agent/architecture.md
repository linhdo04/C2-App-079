# Kiến trúc AI Agent

## Thành phần

### API route

`backend/src/api/routes/agent_routes.py` khai báo `POST /agent/ask`. Route nhận
`question`, gọi `run_agent()` và trả về JSON `{"answer": "..."}`.

### Agent entry point

`backend/src/agent/agent.py` cung cấp:

```python
async def run_agent(question: str) -> str
```

Hàm tạo `AgentState` ban đầu với `question` gốc và `HumanMessage`, gọi
`graph.ainvoke()` rồi ưu tiên trả `state["answer"]`. Nếu graph cũ hoặc fallback
không tạo `answer`, hàm mới đọc content của message cuối.

### State

`backend/src/agent/state.py` định nghĩa state dùng chung:

```python
class AgentState(TypedDict, total=False):
    question: str
    messages: Annotated[list[BaseMessage], add_messages]
    intents: list[str]
    tool_results: dict[str, str]
    tool_errors: dict[str, str]
    answer: str
```

`question` là nguồn input chính cho mọi node. `messages` vẫn được giữ để tương
thích với LangGraph/LangChain, nhưng tool nodes không đọc output của node trước
làm query. `total=False` cho phép mỗi node trả partial state update.

### Graph

`backend/src/agent/graph.py` tạo workflow:

```text
START
  |
  v
route_intent
  |
  v
execute_tools
  |
  v
synthesize_answer
  |
  v
END
```

`route_intent` dùng keyword heuristic để chọn intent:

| Intent | Khi dùng |
| --- | --- |
| `database` | Câu hỏi về user/người dùng/email/tên/dữ liệu nội bộ |
| `weather` | Câu hỏi về thời tiết, dự báo, mưa, nhiệt độ |
| `analysis` | Câu hỏi có diện tích, năng suất hoặc sản lượng |
| `search` | Câu hỏi về giá, thị trường, kỹ thuật, sâu bệnh, cây trồng |
| `general` | Câu hỏi không khớp tool cụ thể |

`execute_tools` chạy các tool khớp intent và lưu kết quả vào `tool_results`.
Lỗi tool được lưu vào `tool_errors` để node tổng hợp có thể nêu hạn chế thay vì
làm hỏng toàn bộ request.

`synthesize_answer` gọi Gemini với `SYSTEM_PROMPT`, câu hỏi gốc, tool results và
tool errors. Nếu Gemini lỗi hoặc trả rỗng, node trả fallback dựa trên dữ liệu đã
có.

## Luồng request

```text
POST /agent/ask
  -> run_agent(question)
  -> AgentState(question, HumanMessage(question))
  -> route_intent
  -> execute_tools
  -> synthesize_answer
  -> {"answer": state["answer"]}
```

## Phụ thuộc bên ngoài

| Hệ thống | Mục đích | Cấu hình |
| --- | --- | --- |
| PostgreSQL | Database tool | `DATABASE_URL` |
| Tavily | Web search | `TAVILY_API_KEY` |
| Open-Meteo | Geocoding và forecast | Không cần API key |
| Google Gemini | Tổng hợp câu trả lời cuối | `GEMINI_API_KEY` |

Xem quyết định nền tảng tại
[ADR 0004](../adr/0004-langchain-gemini.md).
