# Dashboard API

## `GET /dashboard/telemetry`

Trả về các mẫu nhiệt độ và độ ẩm mới nhất từ những cảm biến thuộc mission của
user đang đăng nhập.

### Xác thực

Endpoint yêu cầu access token hợp lệ.

### Query parameters

- `limit`: số mẫu cần lấy, từ `1` đến `100`, mặc định `24`.

### Response

Response dùng envelope `data` và `meta`. Các mẫu trong `data` được sắp xếp theo
thời gian tăng dần để hiển thị trực tiếp trên biểu đồ. Khi nhiều mẫu có cùng
timestamp, `id` được dùng làm tie-breaker để thứ tự luôn xác định.

```json
{
  "data": [
    {
      "timestamp": "2026-06-10T08:30:00Z",
      "temperature_celsius": 28.4,
      "humidity_percent": 72.5,
      "node_name": "Cảm biến môi trường ruộng lúa",
      "mission_name": "Giám sát ruộng lúa mẫu"
    }
  ],
  "meta": {
    "count": 1,
    "limit": 24,
    "latest_timestamp": "2026-06-10T08:30:00Z"
  }
}
```

Giá trị nhiệt độ hoặc độ ẩm có thể là `null` khi cảm biến chỉ gửi một trong hai
chỉ số. Nếu user chưa có telemetry, `data` là mảng rỗng, `count` là `0` và
`latest_timestamp` là `null`.

### Database indexes

Query dashboard được hỗ trợ bởi partial indexes chỉ chứa bản ghi chưa bị
soft-delete:

- `missions(owner_id) WHERE deleted_at IS NULL`
- `iot_nodes(mission_id) WHERE deleted_at IS NULL`
- `telemetry(timestamp, iot_node_id)` với predicate active environmental data

Telemetry index đặt `timestamp` trước để hỗ trợ lấy các mẫu mới nhất với
`ORDER BY timestamp DESC LIMIT ...`. Predicate loại các telemetry không có cả
nhiệt độ lẫn độ ẩm để giảm kích thước và write amplification của index.
