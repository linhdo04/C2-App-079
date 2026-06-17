# Agent Tools

Mỗi production tool kế thừa `Tool`, khai báo Pydantic `input_model` và nhận
validated model trong `execute()`.

| Tool | Input | Ghi chú |
| --- | --- | --- |
| `calculator` | `expression` | AST giới hạn độ dài, depth, operator và magnitude |
| `search` | `query`, `max_results` | Tavily, trả nội dung kèm link nguồn khi có, idempotent và retryable |
| `telemetry` | `limit` | lọc theo authenticated user ownership |
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
