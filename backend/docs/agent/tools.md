# Agent Tools

Mỗi production tool kế thừa `Tool`, khai báo Pydantic `input_model` và nhận
validated model trong `execute()`.

| Tool | Input | Ghi chú |
| --- | --- | --- |
| `calculator` | `expression` | AST giới hạn độ dài, depth, operator và magnitude |
| `search` | `query`, `max_results` | Tavily, trả nội dung kèm link nguồn khi có, idempotent và retryable |
| `telemetry` | `limit`, `relative_range`, `start_time`, `end_time` | lọc theo authenticated user ownership; hỗ trợ “N ngày/tuần/tháng qua”, “tuần này”, “tháng này”, “tuần trước”, “tháng trước”, “hôm nay”, “hôm qua”, hoặc khoảng A-B |
| `analysis` | crop, area, yield, season | tính sản lượng khi đủ dữ liệu |

`Executor` không retry input validation, unknown tool hoặc permanent exception.
Timeout, network và HTTP 429 chỉ retry khi tool khai báo cả `idempotent=True`
và `retryable=True`.

Để thêm tool:

1. Tạo input model.
2. Implement `Tool.execute()`.
3. Đăng ký trong `create_default_agent()`.
4. Thêm success/failure/security tests.
5. Cập nhật tài liệu nếu capability công khai thay đổi.

## Telemetry time ranges

`telemetry` mặc định lấy `limit` mẫu mới nhất. Khi user hỏi theo thời gian,
tool có thể dùng:

- `relative_range`: `last_7_days`, `last_30_days`, `previous_week`,
  `previous_month`, `current_week`, `current_month`, `today`, hoặc
  `yesterday`.
- `start_time` / `end_time`: timestamp explicit. Datetime không có timezone được
  hiểu theo `Asia/Ho_Chi_Minh` rồi convert sang UTC để query.

Quy ước ngôn ngữ tự nhiên: “1 tuần/tháng qua” là rolling interval; “tuần
trước/tháng trước” là kỳ lịch trước theo giờ Việt Nam; “tuần này/tháng này” bắt
đầu từ đầu kỳ hiện tại đến thời điểm query. Parser deterministic cũng hiểu
`N ngày/tuần/tháng qua/gần đây/vừa qua` và date tiếng Việt như `ngày 1 tháng 6
năm 2026`. Date-only explicit range bao gồm trọn ngày bắt đầu và ngày kết thúc.

Với range query, tool dùng SQL aggregation (`count`, `avg`, `min`, `max`) và
query riêng mẫu mới nhất để tránh load toàn bộ telemetry khi user hỏi khoảng lớn.
Nếu range không có dữ liệu, agent báo rõ thiếu telemetry và không dùng `search`
để thay thế trừ khi user hỏi rõ nguồn ngoài/dự báo/web. Câu ngày mơ hồ như
“ngày 18” phải được hỏi lại tháng/năm thay vì tự suy đoán.
