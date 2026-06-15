# Phát triển AI Agent

Chạy từ `backend/`:

```bash
make format
make lint
make check
```

Unit tests dùng fake reasoner/tool, không cần network hay API cost. Integration
Gemini phải opt-in bằng `RUN_AGENT_INTEGRATION_TESTS=1`.

Các contract bắt buộc cần test khi thay đổi agent:

- Pydantic tool input validation.
- retry/backoff chỉ cho transient error.
- `done`, `max_iterations`, `no_progress`, `reasoner_error`.
- recent history ordering/window/character budget.
- tool status xuất hiện trước tool completion.
- incremental token và persistence chỉ sau final answer.
- safe error không lộ exception/observation.

Gemini và Tavily cần key tương ứng. `AGENT_DOCUMENT_ROOTS` là danh sách
comma-separated; giá trị rỗng làm document search trả safe “not configured”.
