# Backend Models

Tài liệu này giải thích vai trò của các module trong `backend/src/models/`.

Trong thư mục này:

- Mỗi file Python là một **module**.
- Phần lớn module định nghĩa một **SQLModel model**, tương ứng với một bảng
  PostgreSQL.
- Model vừa mô tả cấu trúc dữ liệu Python, vừa khai báo cột, khóa ngoại, index
  và constraint cho database.

## Quan hệ tổng quan

```text
User
├── Mission
│   ├── IoTNode
│   │   └── Telemetry
│   ├── FlightPath
│   │   └── CoverageResult
│   ├── Report
│   └── ChatHistory
└── ChatSession
    └── ChatHistory
```

Các khóa ngoại hiện được lưu bằng trường `*_id`. Model chưa khai báo ORM
relationship để tự động load object liên quan; code gọi cần query các bảng cần
thiết một cách tường minh.

## `base.py`

Định nghĩa nền tảng dùng chung cho tất cả model.

### `get_utc_now`

Trả về thời gian hiện tại theo UTC và có timezone. Hàm này được dùng làm giá
trị mặc định cho các timestamp cần tạo từ application.

### `BaseModel`

Mọi database model đều kế thừa class này và nhận các trường:

| Trường | Mục đích |
| --- | --- |
| `id` | Khóa chính tự tăng của bản ghi |
| `created_at` | Thời điểm tạo bản ghi |
| `updated_at` | Thời điểm cập nhật gần nhất |
| `deleted_at` | Thời điểm soft delete; `NULL` nghĩa là còn hoạt động |

`validate_assignment=True` giúp kiểm tra lại dữ liệu khi field được thay đổi
sau khi object đã được tạo.

Lưu ý: có `deleted_at` không có nghĩa mọi query tự động bỏ qua dữ liệu đã xóa.
Từng query vẫn phải thêm điều kiện `deleted_at IS NULL`.

## `user.py`

Định nghĩa `UserModel`, tương ứng bảng `users`.

Model này lưu tài khoản đăng nhập và là chủ thể sở hữu dữ liệu trong hệ thống.

| Trường chính | Mục đích |
| --- | --- |
| `name` | Tên hiển thị |
| `email` | Định danh đăng nhập, không được trùng |
| `password_hash` | Mật khẩu đã hash |

`password_hash` bị ẩn khỏi `repr` và `model_dump()` để giảm nguy cơ vô tình
ghi giá trị nhạy cảm vào log hoặc response.

User có thể sở hữu mission, report, chat session và chat history.

## `mission.py`

Định nghĩa:

- `MissionStatus`: các trạng thái hợp lệ của nhiệm vụ.
- `MissionModel`: bảng `missions`.

Mission là đơn vị nghiệp vụ cấp cao, dùng để nhóm thiết bị, đường bay, kết quả
phủ, báo cáo và hội thoại liên quan đến một nhiệm vụ.

| Trường chính | Mục đích |
| --- | --- |
| `name`, `description` | Thông tin mô tả nhiệm vụ |
| `owner_id` | User sở hữu nhiệm vụ |
| `status` | `planned`, `in_progress`, `completed` hoặc `cancelled` |
| `started_at`, `ended_at` | Khoảng thời gian thực hiện |

Database đảm bảo trạng thái hợp lệ và `ended_at` không đứng trước
`started_at`.

## `iot_node.py`

Định nghĩa `IoTNodeModel`, tương ứng bảng `iot_nodes`.

Model đại diện cho một thiết bị gửi dữ liệu, ví dụ drone, trạm cảm biến hoặc
node IoT ngoài đồng.

| Trường chính | Mục đích |
| --- | --- |
| `name`, `node_type` | Tên và loại thiết bị |
| `serial_number` | Số serial duy nhất |
| `mission_id` | Mission mà thiết bị đang phục vụ |
| `latitude`, `longitude` | Vị trí gần nhất hoặc vị trí cố định |
| `last_seen` | Lần cuối hệ thống nhận tín hiệu |
| `node_metadata` | Thuộc tính mở rộng dạng JSON |

Vĩ độ phải nằm trong `-90..90`, kinh độ trong `-180..180`.

## `telemetry.py`

Định nghĩa `TelemetryModel`, tương ứng bảng `telemetry`.

Mỗi record là một lần đo của một IoT node tại một thời điểm. Đây thường là
bảng có tốc độ tăng dữ liệu nhanh nhất.

| Trường chính | Mục đích |
| --- | --- |
| `iot_node_id` | Thiết bị tạo bản ghi |
| `timestamp` | Thời điểm đo |
| `latitude`, `longitude`, `altitude` | Vị trí tại thời điểm đo |
| `velocity`, `heading` | Tốc độ và hướng di chuyển |
| `temperature_celsius` | Nhiệt độ theo độ C |
| `humidity_percent` | Độ ẩm tương đối theo phần trăm |
| `data` | Chỉ số mở rộng dạng JSON |

Nhiệt độ và độ ẩm nằm trong cùng model vì chúng thuộc cùng một observation,
chung thiết bị và timestamp. Hai cột typed giúp validation và truy vấn thống kê
dễ hơn so với lưu trong JSON.

Các giới hạn đáng chú ý:

- `velocity >= 0`.
- `0 <= heading < 360`.
- `temperature_celsius >= -273.15`.
- `0 <= humidity_percent <= 100`.

Index `(iot_node_id, timestamp)` phục vụ truy vấn chuỗi thời gian của một node.

## `flight_path.py`

Định nghĩa `FlightPathModel`, tương ứng bảng `flight_paths`.

Model lưu kế hoạch hoặc kết quả đường bay thuộc một mission.

| Trường chính | Mục đích |
| --- | --- |
| `mission_id` | Mission sở hữu đường bay |
| `name` | Tên đường bay |
| `path` | Danh sách điểm đường đi dạng JSON |
| `total_distance_m` | Tổng quãng đường, đơn vị mét |
| `estimated_duration_s` | Thời gian dự kiến, đơn vị giây |
| `flown` | Đường bay đã được thực hiện hay chưa |

Khoảng cách và thời lượng không được là số âm.

## `coverage_result.py`

Định nghĩa `CoverageResultModel`, tương ứng bảng `coverage_results`.

Model lưu kết quả đánh giá mức độ bao phủ của mission hoặc một đường bay cụ
thể.

| Trường chính | Mục đích |
| --- | --- |
| `mission_id` | Mission được đánh giá |
| `flight_path_id` | Đường bay tạo ra kết quả |
| `coverage_percent` | Tỷ lệ bao phủ trong `0..100` |
| `details` | Chi tiết phân tích dạng JSON |

Một mission có thể có nhiều kết quả để so sánh các đường bay hoặc các lần chạy.

## `report.py`

Định nghĩa `ReportModel`, tương ứng bảng `reports`.

Model lưu báo cáo nghiệp vụ được tạo từ một mission.

| Trường chính | Mục đích |
| --- | --- |
| `mission_id` | Mission được báo cáo |
| `author_id` | User tạo báo cáo |
| `title`, `content`, `summary` | Nội dung báo cáo |
| `attachments` | Danh sách đường dẫn hoặc định danh file |
| `published_at` | Thời điểm công bố |

`published_at=NULL` có thể được dùng để biểu diễn báo cáo nháp.

## `chat_session.py`

Định nghĩa `ChatSessionModel`, tương ứng bảng `chat_sessions`.

Model đại diện cho một cuộc trò chuyện của user với AI Agent. Nó giữ metadata
cấp cuộc trò chuyện, không chứa nội dung từng tin nhắn.

| Trường chính | Mục đích |
| --- | --- |
| `user_id` | User sở hữu cuộc trò chuyện |
| `title` | Tiêu đề hiển thị trong danh sách chat |

Index `(user_id, updated_at)` hỗ trợ lấy danh sách chat gần nhất của một user.
Nội dung tin nhắn được lưu trong `ChatHistoryModel`.

## `chat_history.py`

Định nghĩa:

- `ChatRole`: vai trò của một message.
- `ChatHistoryModel`: bảng `chat_histories`.

Mỗi record là một message trong lịch sử hội thoại.

| Trường chính | Mục đích |
| --- | --- |
| `chat_session_id` | Cuộc trò chuyện chứa message |
| `mission_id` | Mission liên quan, nếu có |
| `user_id` | User liên quan, nếu có |
| `role` | `user`, `assistant`, `system` hoặc `tool` |
| `message` | Nội dung message |
| `chat_metadata` | Metadata mở rộng dạng JSON |
| `timestamp` | Thời điểm message được tạo |

Việc cho phép `mission_id` và `chat_session_id` cùng tồn tại giúp hội thoại có
thể gắn với ngữ cảnh mission trong tương lai.

## `__init__.py`

File này không tạo bảng mới. Nó export các model qua package `models`, cho phép
import ngắn gọn:

```python
from models import TelemetryModel, UserModel
```

Việc import toàn bộ model tại đây cũng giúp Alembic nhìn thấy metadata của các
bảng khi chạy autogenerate migration.

## Luồng dữ liệu ví dụ

Một luồng thu thập dữ liệu có thể diễn ra như sau:

1. Tạo `UserModel` cho người vận hành.
2. Tạo `MissionModel` do user đó sở hữu.
3. Gán một `IoTNodeModel` vào mission.
4. Thiết bị gửi nhiều `TelemetryModel` theo thời gian.
5. Tạo `FlightPathModel` cho kế hoạch bay.
6. Lưu `CoverageResultModel` sau khi phân tích dữ liệu.
7. Tạo `ReportModel` để tổng hợp kết quả.
8. User trao đổi với Agent qua `ChatSessionModel` và `ChatHistoryModel`.

## Khi thay đổi model

Khi thêm, xóa hoặc đổi cột:

1. Cập nhật model trong `backend/src/models/`.
2. Tạo migration mới bằng:

   ```bash
   cd backend
   make db-migrate m='mo ta thay doi'
   ```

3. Kiểm tra migration được sinh ra.
4. Cập nhật hoặc thêm test model.
5. Chạy `make db-upgrade`.
6. Chạy `make check`.

Không chỉnh sửa migration lịch sử đã được áp dụng.
