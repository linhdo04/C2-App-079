# Agent Tools

Tools nằm trong `backend/src/agent/tools/` và được export từ
`backend/src/agent/tools/__init__.py`.

## Web search

```python
@tool
def web_search(query: str) -> str
```

Tool gọi Tavily với tối đa 5 kết quả và ghép `title`, `content` thành một chuỗi.
Tool là synchronous; node ưu tiên `.ainvoke()` nếu LangChain wrapper hỗ trợ,
hoặc chạy sync call trong thread để tránh block event loop.

Lỗi từ Tavily được node bắt và lưu vào `tool_errors["search"]`.

## Environment telemetry

```python
@tool
async def analyze_environment_telemetry(user_id: int, limit: int = 50) -> str
```

Tool join `telemetry -> iot_nodes -> missions`, chỉ lấy dữ liệu từ mission có
`owner_id` bằng user đang đăng nhập và bỏ qua các bản ghi đã soft-delete. Tool
lấy tối đa 100 mẫu mới nhất có nhiệt độ hoặc độ ẩm, rồi tính giá trị mới nhất,
trung bình, thấp nhất và cao nhất cho từng chỉ số.

Kết quả luôn ghi rõ đây là số đo lịch sử trong database, không phải dự báo thời
tiết.

## Crop analysis

```python
@tool
async def analyze_crop_data(data: dict[str, Any]) -> str
```

Tool tính:

```text
tổng sản lượng = diện tích * năng suất trên mỗi hecta
```

Khuyến nghị hiện dựa trên ngưỡng năng suất `> 5` tấn/ha. Tool được route khi
câu hỏi chứa tín hiệu về diện tích, năng suất hoặc sản lượng. Parser input hiện
chỉ trích xuất số liệu đơn giản từ câu hỏi, hỗ trợ các dạng như `10 ha`, `10ha`,
`ha 10`, `ha10`, `6 tấn/ha`, `6tấn/ha`, `năng suất 6` và số thập phân dùng dấu
phẩy. Keyword số liệu cũng được match theo ranh giới chữ để tránh bắt nhầm
substring. Nếu thiếu diện tích hoặc năng suất hợp lệ, tool trả yêu cầu bổ sung
dữ liệu và không đưa ra phép tính hay đánh giá năng suất.

## Thêm hoặc thay đổi tool

Khi thêm tool:

1. Đặt implementation trong `backend/src/agent/tools/`.
2. Export tool từ `tools/__init__.py`.
3. Thêm runner trong `nodes.py` nếu tool chạy qua LangGraph.
4. Cập nhật heuristic routing nếu tool cần intent mới hoặc keyword mới.
5. Thêm success, failure và regression tests phù hợp.
6. Cập nhật `README.md`, `architecture.md` và file này nếu workflow thay đổi.

Không giả định rằng export một tool sẽ tự động làm tool đó khả dụng trong graph.
Tool phải được route và gọi rõ ràng trong workflow.
