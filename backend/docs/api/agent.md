# Agent API

## Overview

AI Agent cho nông nghiệp Việt Nam, được xây dựng bằng LangChain + LangGraph. Agent có khả năng trả lời câu hỏi về kỹ thuật canh tác, phân tích dữ liệu, dự báo thời tiết.

## Endpoint

### POST /agent/ask

Gửi câu hỏi cho agent và nhận câu trả lời.

**Request:**

```json
{
  "question": "string"
}
```

**Response (200):**

```json
{
  "answer": "string"
}
```

**Errors:**

- `500 Internal Server Error` — Lỗi từ agent hoặc tools. Response body chứa `detail` message.

## Architecture

### Agent Components

Agent được xây dựng với các thành phần:

1. **LLM**: Google Gemini 2.0 Flash (via `langchain_google_genai`)
2. **Graph**: LangGraph StateGraph để điều phối workflow
3. **Tools**: Các công cụ chuyên biệt cho nông nghiệp

### Available Tools

#### 1. Database Tool (`query_crop_database`)

Truy vấn database nội bộ cho thông tin về:
- Người dùng (user)
- Dữ liệu mùa vụ (crop data)

```python
async def query_crop_database(query: str) -> str
```

#### 2. Web Search Tool (`web_search`)

Tìm kiếm thông tin mới nhất từ web về:
- Giá nông sản
- Kỹ thuật canh tác
- Dịch bệnh cây trồng

```python
def web_search(query: str) -> str
```

Powered by Tavily API.

#### 3. Weather Forecast Tool (`get_weather_forecast`)

Dự báo thời tiết cho vùng trồng trọt:
- Nhiệt độ tối thiểu/tối đa
- Lượng mưa
- Tối đa 7 ngày

```python
async def get_weather_forecast(location: str, days: int = 7) -> str
```

Powered by Open-Meteo API.

#### 4. Analysis Tool (`analyze_crop_data`)

Phân tích dữ liệu canh tác và đưa ra khuyến nghị:
- Năng suất
- Sản lượng
- Khuyến nghị cải thiện

```python
async def analyze_crop_data(data: dict[str, Any]) -> str
```

### System Prompt

Agent sử dụng system prompt được tối ưu cho nông nghiệp Việt Nam:

```python
SYSTEM_PROMPT = """
Bạn là trợ lý AI chuyên về nông nghiệp Việt Nam.
Bạn có thể:
- Trả lời câu hỏi về kỹ thuật canh tác, phòng trừ sâu bệnh
- Phân tích dữ liệu mùa vụ, năng suất, giá nông sản
- Cung cấp thông tin thời tiết để hỗ trợ quyết định sản xuất
- Tìm kiếm thông tin mới nhất từ web

Khi trả lời, hãy:
1. Ưu tiên dùng dữ liệu từ database nội bộ trước
2. Bổ sung bằng web search nếu cần thông tin mới
3. Luôn nêu nguồn dữ liệu và mức độ tin cậy
4. Đưa ra khuyến nghị thực tế, phù hợp điều kiện Việt Nam
"""
```

## Configuration

### Environment Variables

Cần thiết lập các environment variables sau:

```bash
# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key

# Tavily Web Search API
TAVILY_API_KEY=your_tavily_api_key

# Database (Postgres)
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db
```

### Dependencies

```toml
dependencies = [
    "langchain>=1.3.4",
    "langgraph>=1.2.4",
    "langchain_google_genai>=4.2.4",
    "tavily_python>=0.7.25",
]
```

## Examples

### Example 1: Weather Forecast

**Request:**

```bash
curl -X POST http://localhost:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Dự báo thời tiết ở Hà Nội 3 ngày tới"}'
```

**Response:**

```json
{
  "answer": "Dự báo thời tiết cho Hanoi trong 3 ngày:\n- 2026-06-08: 25°C - 32°C, mưa 0 mm\n- 2026-06-09: 26°C - 33°C, mưa 5 mm\n- 2026-06-10: 24°C - 31°C, mưa 10 mm"
}
```

### Example 2: Database Query

**Request:**

```bash
curl -X POST http://localhost:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Cho tôi danh sách người dùng"}'
```

**Response:**

```json
{
  "answer": "Danh sách người dùng:\n- id=1, name=John, email=john@example.com\n- id=2, name=Jane, email=jane@example.com"
}
```

### Example 3: Web Search

**Request:**

```bash
curl -X POST http://localhost:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Giá lúa gạo hiện nay"}'
```

**Response:**

```json
{
  "answer": "Thông tin về giá lúa gạo hiện nay:\n- Nguồn 1: Giá lúa hôm nay...\n- Nguồn 2: Thị trường gạo..."
}
```

## Implementation Details

### File Structure

```
src/agent/
├── __init__.py          # Exports: graph, run_agent, tools, AgentState
├── agent.py             # Main agent logic với run_agent()
├── graph.py             # LangGraph StateGraph definition
├── nodes.py             # Graph nodes (wrappers cho tools)
├── state.py             # AgentState TypedDict
├── prompts.py           # System prompt
└── tools/
    ├── __init__.py      # Export all tools
    ├── analysis.py      # Data analysis tool
    ├── database.py      # Database query tool
    ├── search.py        # Web search tool
    └── weather.py       # Weather forecast tool
```

### Agent Flow

1. User gửi question qua POST /agent/ask
2. FastAPI route gọi `run_agent(question)`
3. Agent tạo initial state với user message
4. LangGraph graph invoke các nodes theo workflow
5. Nodes gọi tools và trả về kết quả
6. Agent trả về câu trả lời cuối cùng

### Error Handling

Agent có error handling ở nhiều layers:

- **Tool level**: Mỗi tool handle errors riêng (API failures, DB errors)
- **Agent level**: `run_agent()` catch và log exceptions
- **API level**: FastAPI route trả về 500 với error detail

## Testing

### Unit Test Tools

```bash
pytest tests/test_tools.py
```

### Integration Test Agent

```bash
python test_agent.py
```

### Manual Test via API

```bash
# Start server
make run

# Test endpoint
curl -X POST http://localhost:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "test question"}'
```

## Performance Considerations

- **LLM calls**: Mỗi agent call invoke LLM, thời gian response 1-3s
- **Tool caching**: Database và web search results có thể cache
- **Async tools**: Weather và database tools đều async để improve performance
- **Rate limiting**: Có rate limiting middleware ở API level

## Future Improvements

- [ ] Add streaming support cho real-time responses
- [ ] Implement tool result caching
- [ ] Add conversation history management
- [ ] Support multi-turn dialogues
- [ ] Add more agricultural tools (soil data, crop recommendations)
- [ ] Implement RAG cho domain knowledge
