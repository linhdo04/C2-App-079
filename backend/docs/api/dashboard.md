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
thời gian tăng dần để hiển thị trực tiếp trên biểu đồ.

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
