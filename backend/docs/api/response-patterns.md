# API Response Patterns

Các JSON endpoint của backend dùng một contract thống nhất.

## Object response

```json
{
  "data": {
    "id": 1
  }
}
```

## Collection response

```json
{
  "data": [],
  "meta": {
    "count": 0
  }
}
```

Collection có thể mở rộng `meta` bằng metadata đặc thù như `limit` hoặc
`latest_timestamp`. Dữ liệu nghiệp vụ luôn nằm trong `data`.

Collection dùng cursor pagination có thêm:

```json
{
  "meta": {
    "count": 20,
    "limit": 20,
    "has_more": true,
    "next_cursor": "opaque-cursor"
  }
}
```

`next_cursor` là opaque và chỉ được gửi lại nguyên trạng; client không dựa vào
cấu trúc bên trong cursor.

## Error response

```json
{
  "error": "validation_error",
  "message": "Request validation failed.",
  "details": [
    {
      "field": "body → email",
      "message": "value is not a valid email address",
      "type": "value_error"
    }
  ]
}
```

- `error`: mã ổn định để client xử lý bằng code.
- `message`: thông báo có thể hiển thị hoặc ghi log.
- `details`: tùy chọn, chứa lỗi field hoặc metadata bổ sung.
- HTTP status vẫn là nguồn chính để xác định kết quả request.

## Protocol exceptions

- `POST /auth/token` giữ response OAuth2 chuẩn với `access_token` ở top-level.
- Response `204 No Content` không có body.
- SSE giữ framing `event`/`data`; payload thành công nằm trong `data`, payload
  lỗi dùng `error` và `message`.
