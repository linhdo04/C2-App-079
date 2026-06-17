# Drone API

## `POST /drones/telemetry`

Nhận telemetry từ drone, lưu vào bảng `telemetry`, và cập nhật `last_seen` cùng
tọa độ hiện tại của `iot_nodes` khi payload có `latitude` hoặc `longitude`.

### Xác thực

Endpoint dùng header `X-API-Key`. Giá trị hợp lệ được cấu hình bằng biến môi
trường `DRONE_API_KEY`.

### Request

Payload phải có một trong hai định danh node:

- `iot_node_id`: id nội bộ của node.
- `serial_number`: serial number của node đã đăng ký trong bảng `iot_nodes`.

```json
{
  "serial_number": "DRONE-001",
  "timestamp": "2026-06-17T08:30:00Z",
  "latitude": 10.5,
  "longitude": 106.7,
  "altitude": 120,
  "velocity": 8.5,
  "heading": 45,
  "temperature_celsius": 31.2,
  "humidity_percent": 70,
  "data": {
    "battery_percent": 86
  }
}
```

Nếu không gửi `timestamp`, server tự dùng thời điểm hiện tại.

### Response

```json
{
  "data": {
    "id": 42,
    "iot_node_id": 7,
    "timestamp": "2026-06-17T08:30:00Z"
  }
}
```

### Errors

- `401`: thiếu hoặc sai `X-API-Key`.
- `404`: không tìm thấy node active theo `iot_node_id` hoặc `serial_number`.
- `422`: payload không hợp lệ.
- `503`: server chưa cấu hình `DRONE_API_KEY`.
