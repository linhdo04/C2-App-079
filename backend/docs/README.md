# Documentation

Thư mục `docs/` chứa tài liệu kỹ thuật cho backend project C2-App-079.

## Structure

### `architecture/`
Kiến trúc hệ thống, diagrams và mô tả chi tiết:
- [architecture.mmd](architecture/architecture.mmd) - System architecture diagram
- [agent-architecture.md](architecture/agent-architecture.md) - **AI Agent Architecture** (LangGraph, tools, workflow)
- [README.md](architecture/README.md) - Architecture overview

### `api/`
API documentation chi tiết về endpoints, request/response:
- [health.md](api/health.md) - Health check endpoint
- [agent.md](api/agent.md) - **AI Agent API** (POST /agent/ask)
- [README.md](api/README.md) - API overview

### `adr/`
Architecture Decision Records - các quyết định quan trọng:
- [0001-fastapi.md](adr/0001-fastapi.md) - FastAPI framework
- [0002-sqlmodel-postgres.md](adr/0002-sqlmodel-postgres.md) - SQLModel + PostgreSQL
- [0003-redis-rate-limiting.md](adr/0003-redis-rate-limiting.md) - Redis rate limiting
- [0004-langchain-gemini.md](adr/0004-langchain-gemini.md) - **LangChain + Gemini AI**

### `core-architecture.md`
[Tài liệu tổng quan về kiến trúc core](core-architecture.md) - Database, API, middleware, configuration.

## Quick Links

### AI Agent
- **API Documentation**: [api/agent.md](api/agent.md)
- **Architecture**: [architecture/agent-architecture.md](architecture/agent-architecture.md)
- **ADR**: [adr/0004-langchain-gemini.md](adr/0004-langchain-gemini.md)

### Getting Started
1. Đọc [core-architecture.md](core-architecture.md) để hiểu tổng quan hệ thống
2. Xem [api/](api/) để biết các endpoints khả dụng
3. Tham khảo [architecture/](architecture/) để hiểu sâu về thiết kế
4. Đọc [adr/](adr/) để biết lý do đằng sau các quyết định kỹ thuật

## Contributing

Khi thêm tính năng mới:
1. Update API docs trong `api/`
2. Update architecture docs nếu thay đổi thiết kế
3. Tạo ADR mới nếu có quyết định kiến trúc quan trọng
4. Update README này với links mới

## Notes

- Tất cả docs được viết bằng Markdown
- Diagrams sử dụng Mermaid format (.mmd)
- API examples sử dụng cURL và JSON
- Code examples sử dụng Python với type hints
