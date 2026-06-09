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
  "answer": "Theo dữ liệu thời tiết hiện có..."
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

Trả danh sách chat mới cập nhật trước. Dùng `?search=lúa` để tìm không phân biệt
hoa thường trong cả tiêu đề và nội dung message.

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
data: {"phase":"routing","message":"Đang phân tích yêu cầu..."}
```

Khi chạy tool, payload có thêm tên tool:

```text
event: status
data: {"phase":"tool","tool":"weather","message":"Đang lấy dữ liệu thời tiết..."}
```

Token event:

```text
event: token
data: {"content":"Theo "}
```

Khi câu trả lời đã được lưu:

```text
event: done
data: {"chat":{...},"user_message":{...},"assistant_message":{...}}
```

Nếu lỗi xảy ra sau khi stream bắt đầu:

```text
event: error
data: {"detail":"..."}
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

Graph hiện vẫn xử lý riêng câu hỏi mới nhất. Lịch sử chat được lưu và hiển thị
nhưng chưa được đưa vào context của LLM.
