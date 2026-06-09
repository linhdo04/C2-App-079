# Agent API

API này cho phép client gửi một câu hỏi độc lập tới AI Agent và nhận lại câu
trả lời dạng chuỗi.

Endpoint yêu cầu JWT Bearer token trong header `Authorization`.

Implementation chi tiết của agent nằm trong [`docs/agent/`](../agent/README.md).

## Endpoint

### POST /agent/ask

Gửi câu hỏi cho agent.

**Request body:**

```json
{
  "question": "string"
}
```

**Response 200:**

```json
{
  "answer": "string"
}
```

**Errors:**

- `500 Internal Server Error`: lỗi không mong muốn từ agent. Lỗi từ tool phụ như
  Tavily hoặc Open-Meteo được agent cố gắng fallback mềm khi còn dữ liệu khác.
- `401 Unauthorized`: thiếu hoặc sai Bearer token.

## Ví dụ

```bash
curl -X POST http://localhost:8000/agent/ask \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"question": "Dự báo thời tiết ở Hà Nội"}'
```

Response:

```json
{
  "answer": "Theo dữ liệu thời tiết hiện có, Hà Nội..."
}
```

## Ghi chú implementation

- Route gọi `run_agent(question)` trong `backend/src/agent/agent.py`.
- Graph hiện route intent, chạy tool phù hợp và dùng Gemini tổng hợp câu trả lời.
- Response ưu tiên `answer` trong graph state.
- API hiện chưa hỗ trợ conversation history, streaming hoặc session memory.

Xem thêm:

- [Tổng quan agent](../agent/README.md)
- [Kiến trúc agent](../agent/architecture.md)
- [Agent tools](../agent/tools.md)
