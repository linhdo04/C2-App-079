# Agent API

Các endpoint bên dưới nằm dưới `API_PREFIX`. Với `API_PREFIX=/api`,
`POST /agent/ask` có URL đầy đủ là `POST /api/agent/ask`. Endpoint yêu cầu JWT
Bearer token và dữ liệu chat luôn được lọc theo user đang đăng nhập.

## Hỏi độc lập

### POST /agent/ask

```json
{
  "question": "Dự báo thời tiết ở Hà Nội"
}
```

Response:

```json
{
  "data": {
    "answer": "Theo dữ liệu thời tiết hiện có..."
  }
}
```

## Quản lý chat

### POST /agent/chats

Tạo chat mới. Body có thể rỗng hoặc chứa `title`.

```json
{
  "title": "Kế hoạch vụ hè thu"
}
```

### GET /agent/chats

Trả danh sách chat mới cập nhật trước trong `data`, kèm `meta.count`. Dùng
`?search=lúa` để tìm không phân biệt hoa thường trong cả tiêu đề và nội dung
message.

Query parameters:

- `limit`: số chat mỗi trang, từ `1` đến `100`, mặc định `20`.
- `cursor`: cursor opaque nhận từ `meta.next_cursor` của trang trước.
- `search`: tìm trong tiêu đề và nội dung message, tối đa `120` ký tự.

```json
{
  "data": [
    {
      "id": 42,
      "title": "Kế hoạch vụ hè thu",
      "created_at": "2026-06-11T01:00:00Z",
      "updated_at": "2026-06-11T02:00:00Z"
    }
  ],
  "meta": {
    "count": 1,
    "limit": 20,
    "has_more": true,
    "next_cursor": "eyJ2ZXJzaW9uIjoxLC4uLn0"
  }
}
```

Client không được giải mã, chỉnh sửa hoặc tự tạo cursor. Cursor được backend ký
để phát hiện thay đổi và chỉ lưu digest của search context, không chứa search
text dạng rõ. Khi `has_more=true`, gửi nguyên `next_cursor` vào request tiếp
theo cùng giá trị `search`. Cursor không hợp lệ hoặc không khớp search trả
`400 bad_request`.

Pagination dùng keyset `(updated_at DESC, id DESC)`, tránh chi phí và sai lệch
của offset khi chat mới được tạo hoặc cập nhật giữa các request.

### GET /agent/chats/{chat_id}

Trả thông tin chat và toàn bộ message chưa bị xoá, theo thứ tự thời gian tăng
dần.

### POST /agent/chats/{chat_id}/messages

Gửi câu hỏi, chạy agent và lưu cả user message lẫn assistant message. Chat mặc
định được đổi tên theo câu hỏi đầu tiên. Endpoint này trả JSON hoàn chỉnh và
được giữ để tương thích.

```json
{
  "question": "Tuần này nên điều chỉnh lịch phun thuốc thế nào?"
}
```

### POST /agent/chats/{chat_id}/messages/stream

Gửi cùng request body như endpoint message thường nhưng trả
`Content-Type: text/event-stream`.

Status event:

```text
event: status
data: {"data":{"phase":"routing","message":"Đang phân tích yêu cầu..."}}
```

Khi chạy tool, payload có thêm tên tool:

```text
event: status
data: {"data":{"phase":"tool","tool":"telemetry","message":"Đang phân tích nhiệt độ và độ ẩm..."}}
```

Token event:

```text
event: token
data: {"data":{"content":"Theo "}}
```

Khi câu trả lời đã được lưu:

```text
event: done
data: {"data":{"chat":{...},"user_message":{...},"assistant_message":{...}}}
```

Nếu lỗi xảy ra sau khi stream bắt đầu:

```text
event: error
data: {"error":"stream_error","message":"..."}
```

Backend chỉ lưu lịch sử sau khi nhận đầy đủ câu trả lời. Nếu stream hoặc thao
tác database lỗi, transaction được rollback.

### DELETE /agent/chats/{chat_id}

Soft-delete chat và trả `204 No Content`.

## Errors

- `401 Unauthorized`: token thiếu, sai hoặc hết hạn.
- `404 Not Found`: chat không tồn tại, đã xoá hoặc không thuộc current user.
- `422 Unprocessable Entity`: request không hợp lệ.
- `500 Internal Server Error`: agent không thể tạo câu trả lời.

Chat message endpoints đưa recent history thuộc chính user/chat vào context của
agent. `/agent/ask` vẫn stateless.
