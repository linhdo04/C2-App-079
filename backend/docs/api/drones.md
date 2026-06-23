# Drone API

## `POST /api/drones/nodes/{iot_node_id}/api-key`

Tạo hoặc rotate API key cho một IoT node thuộc mission của user hiện tại. Key
plaintext chỉ trả về một lần trong response; server chỉ lưu hash ở
`iot_nodes.api_key_hash`.

### Xác thực

Endpoint này dùng session đăng nhập của operator (`HttpOnly` access cookie hoặc
OAuth bearer token). User chỉ tạo key được cho node thuộc mission do mình sở hữu.

### Response

```json
{
  "data": {
    "iot_node_id": 7,
    "api_key": "drn_example-generated-secret"
  }
}
```

### Errors

- `401`: chưa đăng nhập hoặc user không hợp lệ.
- `404`: không tìm thấy node active thuộc user hiện tại.

## `POST /api/drones/telemetry`

Nhận telemetry từ drone, lưu vào bảng `telemetry`, và cập nhật `last_seen` cùng
tọa độ hiện tại của `iot_nodes` khi payload có `latitude` hoặc `longitude`.

### Xác thực

Endpoint dùng header `X-API-Key`. Giá trị hợp lệ là API key đã tạo cho đúng
`iot_node_id` hoặc `serial_number` của node đích; key của node khác sẽ bị từ
chối.

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

- `401`: thiếu `X-API-Key`, sai key, hoặc key không khớp node.
- `404`: không tìm thấy node active theo `iot_node_id` hoặc `serial_number`.
- `422`: payload không hợp lệ.
