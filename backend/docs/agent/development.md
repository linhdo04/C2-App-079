# Phát triển AI Agent

## Thiết lập

Chạy các lệnh từ thư mục `backend/`.

Các biến môi trường liên quan:

```bash
GEMINI_API_KEY=<required-to-initialize-model>
TAVILY_API_KEY=<required-for-web-search>
AGENT_TOOL_TIMEOUT_SECONDS=15
AGENT_LLM_TIMEOUT_SECONDS=20
```

Telemetry tool dùng PostgreSQL đã cấu hình cho backend.

## Demo data

Sau khi chạy migration, tạo tài khoản, mission, sensor và 24 mẫu telemetry:

```bash
make db-upgrade
make db-seed
```

Thông tin đăng nhập:

```text
Email: demo@aerofield.example.com
Password: Demo12345!
```

Seed là idempotent: chạy lại sẽ cập nhật tài khoản demo và thay thế telemetry
của sensor `DEMO-ENV-001`, không xóa dữ liệu khác.

## Chạy ứng dụng

```bash
make run
```

Gọi API:

```bash
curl -X POST http://localhost:8000/agent/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Dự báo thời tiết ở Hà Nội"}'
```

API contract chi tiết nằm tại [Agent API](../api/agent.md).

## Gọi agent trong Python

```python
from agent import run_agent

answer = await run_agent("Phân tích nhiệt độ và độ ẩm", user_id=7)
```

LangChain tools phải được gọi bằng `.invoke()` hoặc `.ainvoke()`:

```python
from agent.tools import web_search

results = web_search.invoke({"query": "giá lúa"})
```

## Kiểm thử

Chạy agent tests:

```bash
pytest tests/test_agent.py
```

Chạy toàn bộ bộ kiểm tra backend:

```bash
make format
make lint
make check
```

Các test liên quan đến Tavily, Gemini hoặc database nên mock boundary
bên ngoài để ổn định và không phụ thuộc API key/network trong unit tests. Bộ
test mặc định của agent dùng mock offline.

Khi thay đổi graph, tối thiểu cần kiểm tra:

- state ban đầu chứa đúng `HumanMessage`;
- `question` gốc được giữ và tool nodes đọc `state["question"]`;
- routing chọn đúng intent;
- tool results và tool errors được lưu riêng;
- output cuối được lấy từ `state["answer"]`;
- output fallback khi graph không có message;
- exception được chuyển tiếp;
- API trả đúng schema và status code.

## Quy tắc thay đổi

Trước khi sửa agent code:

1. Đọc [tổng quan](README.md), [kiến trúc](architecture.md) và
   [tools](tools.md).
2. Xác định tác động đến prompt, graph, tools và state.
3. Giữ API contract và state compatibility nếu không có yêu cầu thay đổi.
4. Thêm hoặc cập nhật tests cho hành vi mới.
5. Cập nhật docs trong cùng thay đổi nếu workflow hoặc cấu hình thay đổi.

Không chỉnh graph chỉ để khớp tài liệu. Tài liệu phải phản ánh code đang chạy;
thay đổi hành vi agent cần được xử lý như một task implementation riêng.
