# AI Agent

Tài liệu này mô tả AI Agent trong `backend/src/agent/` theo implementation hiện
tại. Bắt đầu từ đây trước khi thay đổi prompt, graph, tools hoặc state.

## Mục lục

- [Kiến trúc và luồng xử lý](architecture.md)
- [Danh sách tools](tools.md)
- [Hướng dẫn phát triển và kiểm thử](development.md)
- [Agent API](../api/agent.md)
- [ADR: LangChain và Gemini](../adr/0004-langchain-gemini.md)

## Chức năng hiện tại

Agent nhận một câu hỏi qua `POST /agent/ask`, lưu câu hỏi gốc trong
`AgentState`, route intent, chạy tool phù hợp và dùng Gemini tổng hợp câu trả
lời cuối.

Graph hiện chạy theo workflow:

```text
route_intent -> execute_tools -> synthesize_answer -> END
```

Các tool hiện có:

| Tool | Trạng thái trong graph | Mục đích |
| --- | --- | --- |
| `web_search` | Dùng khi intent `search` | Tìm kiếm qua Tavily |
| `analyze_environment_telemetry` | Dùng khi intent `telemetry` | Phân tích nhiệt độ và độ ẩm trong Postgres |
| `analyze_crop_data` | Dùng khi intent `analysis` | Tính sản lượng và đưa ra khuyến nghị đơn giản |

## Giới hạn cần biết

- Intent routing hiện dùng heuristic keyword, chưa phải LLM tool-calling.
- Telemetry node lấy tối đa 50 mẫu nhiệt độ và độ ẩm mới nhất từ các mission
  thuộc user hiện tại, sau đó tính giá trị mới nhất, trung bình, thấp nhất và
  cao nhất. Đây là dữ liệu lịch sử từ database, không phải dự báo thời tiết.
- `analyze_crop_data` chỉ trích xuất dữ liệu rất đơn giản từ câu hỏi, chưa có
  parser mùa vụ phức tạp. Tool không tính hoặc khuyến nghị khi thiếu diện tích
  hay năng suất hợp lệ.
- API lưu lịch sử hỏi đáp theo từng cuộc trò chuyện và hỗ trợ streaming câu trả
  lời cuối qua SSE. Graph vẫn xử lý câu hỏi hiện tại độc lập, chưa đưa các lượt
  trước vào context của LLM và chưa hỗ trợ memory.
- Nếu một tool phụ lỗi, agent lưu lỗi vào state và vẫn cố tổng hợp bằng dữ liệu
  còn lại. Nếu Gemini lỗi, agent trả fallback từ tool results.

Các điểm trên là mô tả trạng thái hiện tại, không phải thiết kế mục tiêu. Khi
thay đổi hành vi, cập nhật tài liệu tương ứng trong thư mục này.

## Cấu trúc mã nguồn

```text
backend/src/agent/
├── __init__.py
├── agent.py
├── graph.py
├── nodes.py
├── prompts.py
├── state.py
└── tools/
    ├── __init__.py
    ├── analysis.py
    ├── search.py
    └── telemetry.py
```
