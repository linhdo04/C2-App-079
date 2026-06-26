# Core Architecture

Tài liệu này mô tả kiến trúc backend hiện tại sau khi đối chiếu với source trong
`backend/src/`, migrations và cấu hình dự án.

## Tổng quan

Backend là một ASGI HTTP service dùng FastAPI, Pydantic Settings, SQLModel,
PostgreSQL, Redis, Structlog và một AI Agent dựa trên ReAct loop riêng,
LangChain và DeepSeek.

Các entry point chính:

- Application: `backend/src/api/main.py`
- Configuration: `backend/src/core/config.py`
- Logging: `backend/src/core/logging.py`
- Infrastructure: `backend/src/infrastructure/`
- Models: `backend/src/models/`
- Agent: `backend/src/agent/`
- Migrations: `backend/migrations/`

ADR liên quan:

- `backend/docs/adr/0001-fastapi.md`
- `backend/docs/adr/0002-sqlmodel-postgres.md`
- `backend/docs/adr/0003-redis-rate-limiting.md`
- `backend/docs/adr/0005-switch-agent-llm-to-deepseek.md`

## Runtime Structure

```text
Client
  |
  v
FastAPI app (`src/api/main.py`)
  |
  +-- RequestLoggingMiddleware
  +-- RateLimitMiddleware
  +-- ErrorHandlingMiddleware
  |
  +-- GET /api/health
  +-- POST /agent/ask
        |
        v
      run_agent(question, user_id)
        |
        v
      ReAct loop: reason -> execute tool -> observe -> final answer
        |
        +-- PostgreSQL telemetry via SQLModel/asyncpg
        +-- Tavily web search
        +-- DeepSeek reasoner/final answer
```

## Application Lifecycle

`src/api/main.py` tạo `FastAPI(lifespan=lifespan)`.

Startup:

1. `setup_logging(level=settings.log_level, json_indent=2)`
2. `init_db()`
3. `init_redis()`
4. Gắn Redis client vào `app.state.redis`

Shutdown:

1. `close_db()`
2. `close_redis()`

`init_redis()` gọi `ping()`, nên Redis connection failure trong startup sẽ làm
lifespan fail. Trong request path, rate limiting fail-open nếu `app.state.redis`
không tồn tại hoặc Redis/script gặp lỗi.

## Configuration

`src/core/config.py` dùng `pydantic-settings` và đọc `.env`.

Các biến được đọc bởi `Settings`:

```env
DEEPSEEK_API_KEY=
DEEPSEEK_API_BASE=
LLM_PROVIDER=
DEFAULT_MODEL=
TAVILY_API_KEY=
APP_NAME=
APP_ENV=
APP_DEBUG=
API_HOST=
API_PORT=
API_PREFIX=
LOG_LEVEL=
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_DB=
POSTGRES_HOST=
POSTGRES_PORT=
REDIS_HOST=
REDIS_PORT=
REDIS_PASSWORD=
```

Một số biến có default trong code: `APP_ENV`, `APP_DEBUG`, `LOG_LEVEL` và
`REDIS_PASSWORD`.

`database_url` được build từ `POSTGRES_*` theo dạng
`postgresql+asyncpg://...`. `redis_url` được build từ `REDIS_*` theo dạng
`redis://:<password>@<host>:<port>`. Nếu `REDIS_PASSWORD` để trống, cần kiểm tra
lại URL thực tế vì property hiện vẫn format phần password.

`API_PREFIX` được áp dụng qua router cha trong `src/api/main.py`. Với cấu hình
`API_PREFIX=/api`, route agent là `/api/agent/ask`.

## HTTP Layer

### Routes

`src/api/routes/agent_routes.py` khai báo:

- `POST /agent/ask`

Request body:

```json
{
  "question": "string"
}
```

Response thành công:

```json
{
  "data": {
    "answer": "string"
  }
}
```

Route gọi `await run_agent(req.question)`. Import `graph` và biến `graph:
Any` vẫn còn trong file route nhưng không tham gia xử lý request hiện tại.

`src/api/main.py` cũng khai báo:

- `GET /api/health` trả `{"data":{"status":"healthy"}}` và không yêu cầu xác
  thực.

Hiện chưa có route `/metrics`, dù rate limiter đang exclude các
path này.

### Middleware

Các middleware được đăng ký trong `src/api/main.py` theo thứ tự source:

1. `RequestLoggingMiddleware`
2. `RateLimitMiddleware`
3. `ErrorHandlingMiddleware`

Với Starlette middleware stack, middleware được đăng ký sau sẽ nằm bên ngoài
middleware đăng ký trước. Vì vậy request runtime đi qua error handling, rate
limiting, rồi request logging trước khi tới router.

#### Request logging

`src/api/middlewares/logging.py`:

- Lấy `X-Correlation-ID` nếu client gửi, nếu không tự tạo UUID.
- Gắn correlation id vào ContextVar qua `set_correlation_id()`.
- Log method, path, query, status code, duration, client IP và user agent.
- Gắn response header `X-Correlation-ID`.

#### Rate limiting

`src/api/middlewares/rate_limiting.py`:

- Dùng Redis sorted set và Lua script sliding window.
- Giới hạn mặc định trong app:
  - IP: 60 requests / 60 giây
  - API key: 600 requests / 60 giây qua header `X-API-Key`
- Nếu có cả IP và API key, kiểm tra cả hai lớp.
- Khi bị chặn trả `429` với `Retry-After`,
  `X-RateLimit-Limit`, `X-RateLimit-Remaining`.
- Nếu Redis không sẵn sàng hoặc script lỗi, middleware cho request đi tiếp và
  log warning.

#### Error handling

`src/api/middlewares/error_handling.py`:

- `RequestValidationError` -> `422 validation_error`
- `HTTPException` -> JSON theo status code
- Exception không dự kiến -> `500 internal_server_error`
- Khi `APP_DEBUG=True`, response 500 có thêm thông tin debug.

## Logging

`src/core/logging.py` cấu hình Structlog output JSON ra stdout. Log record được
inject `correlation_id` từ ContextVar nếu có.

Module này cũng có logging helpers cho request/agent observability. Agent tracing
runtime hiện tại đi qua LangSmith khi cấu hình LangSmith tồn tại.

## Database and Persistence

`src/infrastructure/database/postgres.py` quản lý SQLAlchemy async engine:

- Engine: `create_async_engine(settings.database_url)`
- Pool:
  - `pool_size=10`
  - `max_overflow=20`
  - `pool_pre_ping=True`
- Echo SQL khi `APP_ENV != "production"`
- Session factory: `async_sessionmaker(expire_on_commit=False, autoflush=False)`

Có hai cách lấy session:

- `get_session()` cho FastAPI dependency style.
- `db_session()` cho tools, background tasks hoặc scripts.

Cả hai commit khi thành công và rollback khi có exception.

## Data Model

Tất cả model kế thừa `BaseModel` trong `src/models/base.py`:

- `id`
- `created_at`
- `updated_at`
- `deleted_at`

Các bảng hiện có:

| Model | Table | Ghi chú |
| --- | --- | --- |
| `UserModel` | `users` | `name`, `email` unique |
| `MissionModel` | `missions` | owner user, status, started/ended timestamps |
| `IoTNodeModel` | `iot_nodes` | serial number unique, location, metadata JSON |
| `TelemetryModel` | `telemetry` | node telemetry, timestamp, location, motion, temperature, humidity, data JSON |
| `FlightPathModel` | `flight_paths` | mission path JSON, distance, duration, flown flag |
| `CoverageResultModel` | `coverage_results` | mission/path coverage percentage and details JSON |
| `ReportModel` | `reports` | mission report, author, content, summary, attachments JSON |
| `ChatHistoryModel` | `chat_histories` | mission/user message history and metadata JSON |

Operational notes:

- Foreign keys are indexed, and telemetry/chat history include composite indexes
  for parent-and-timestamp queries.
- Domain ranges and finite status/role values are enforced by both model
  validation and database check constraints.
- `TelemetryModel` is likely the highest-volume table; add a retention policy
  before production ingestion grows.
- `deleted_at` enables soft delete semantics, but no repository/query helper
  currently enforces filtering deleted records.
- JSON fields provide flexibility but need validation at service boundaries.

## Migrations

Alembic config:

- `backend/alembic.ini`
- `backend/migrations/env.py`
- `backend/migrations/versions/`

`migrations/env.py` imports `models`, sets `target_metadata = SQLModel.metadata`
and injects `settings.database_url` into Alembic config.

Existing revisions:

- `1fbf76289c4b_create_users_table.py`
- `956e21bcf9c5_create_models.py`

Make targets:

```bash
make db-migrate m='migration_name'
make db-upgrade
make db-downgrade
```

Do not edit historical migrations. Add a new revision for schema changes.

## Redis

`src/infrastructure/cache/redis.py` owns a module-level `Redis | None` client.

- `init_redis()` creates the client from `settings.redis_url` and pings it.
- `get_redis()` raises if Redis has not been initialized.
- `close_redis()` closes the async client.

Current primary Redis use is rate limiting. The architecture leaves room for
short-lived cache/ephemeral state, but no generic cache abstraction exists yet.

## Agent

Agent docs live in `backend/docs/agent/`.

Current request flow:

```text
POST /agent/ask
  -> run_agent(question, current_user.id)
  -> HumanMessage(question)
  -> DeepSeek-backed reasoner
  -> execute selected tool through Executor
  -> observe sanitized result
  -> repeat until done or max iterations
  -> final answer
```

Important current behavior:

- Telemetry intent reads temperature and humidity observations from PostgreSQL.
- Telemetry queries are filtered through mission ownership using current user ID.
- Telemetry observations are historical measurements, not weather forecasts.
- Search uses Tavily; crop analysis uses values extracted from the question.
- DeepSeek synthesizes the final answer from tool results and tool limitations.

For agent implementation details, use:

- `backend/docs/agent/README.md`
- `backend/docs/agent/architecture.md`
- `backend/docs/agent/tools.md`
- `backend/docs/agent/development.md`

## Testing and Quality

Project config is in `backend/pyproject.toml`.

Main commands:

```bash
make format
make lint
make check
```

`make check` runs:

1. `ruff check .`
2. `ruff format --check .`
3. `mypy .`
4. `pytest`

Current tests:

- `tests/test_main.py`: placeholder assertions.
- `tests/test_agent.py`: integration-style agent smoke test that can require
  configured external dependencies and database/Redis state.

When adding backend behavior, prefer unit tests that mock external boundaries
such as Tavily, Open-Meteo, DeepSeek, Redis and Postgres.

## Deployment Notes

- Run with an ASGI server. The local Make target uses:

```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

- Scale horizontally by running multiple app instances sharing PostgreSQL and
  Redis.
- Keep secrets in environment variables or a secret manager, not in source.
- Redis rate limiting is safe for multiple instances because checks are atomic
  Lua scripts.
- Mở rộng health check thành readiness check nếu orchestration cần kiểm tra
  PostgreSQL hoặc Redis.
- Add metrics/tracing if agent latency and tool failures need operational
  visibility.

## Known Gaps

- `/metrics` được exclude khỏi rate limiting nhưng chưa được implement.
- Agent docs describe current limitations and the current ReAct runtime.
- Soft delete is modeled but not enforced by query helpers.
- Current tests are minimal and do not cover middleware, database sessions,
  migrations or agent tool failure paths.
