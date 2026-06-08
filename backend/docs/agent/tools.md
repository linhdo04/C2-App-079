# Agent Tools

Tools nằm trong `backend/src/agent/tools/` và được export từ
`backend/src/agent/tools/__init__.py`.

## Database

```python
@tool
async def query_crop_database(query: str) -> str
```

Tool chuẩn hóa query về lowercase và kiểm tra các keyword liên quan đến user.
Nếu khớp, tool lấy tối đa 100 `UserModel` từ Postgres và chỉ trả `id`, `name`;
email không được đưa vào kết quả.

Nếu query không liên quan đến user, tool trả thông báo rằng schema chưa có dữ
liệu mùa vụ. Đây chưa phải text-to-SQL.

## Web search

```python
@tool
def web_search(query: str) -> str
```

Tool gọi Tavily với tối đa 5 kết quả và ghép `title`, `content` thành một chuỗi.
Tool là synchronous; node ưu tiên `.ainvoke()` nếu LangChain wrapper hỗ trợ,
hoặc chạy sync call trong thread để tránh block event loop.

Lỗi từ Tavily được node bắt và lưu vào `tool_errors["search"]`.

## Weather

```python
@tool
async def get_weather_forecast(location: str, days: int = 7) -> str
```

Tool:

1. Giới hạn `days` trong khoảng 1 đến 7.
2. Chấp nhận location dạng tên địa điểm hoặc `lat,lon`.
3. Geocode tên địa điểm qua Open-Meteo khi chưa có tọa độ.
4. Lấy nhiệt độ tối đa, tối thiểu và lượng mưa theo ngày.
5. Trả kết quả theo timezone `Asia/Bangkok`.

HTTP timeout là 10 giây. Các response status không thành công và trường hợp
không có dữ liệu được chuyển thành thông báo tiếng Việt.

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
chỉ trích xuất số liệu đơn giản từ câu hỏi.

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
