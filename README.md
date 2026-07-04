# Team 079 — Autonomous Drones

Ứng dụng quản lý drone tự hành, gồm dashboard giám sát, quản lý nhiệm vụ,
telemetry và AI Agent hỗ trợ vận hành.

## Công nghệ

- Backend: FastAPI, SQLModel, PostgreSQL, Redis, LangGraph
- Frontend: Next.js 16, React 19, TypeScript, Tailwind CSS
- Infrastructure: Docker Compose và Kubernetes

## Thành viên

- Đỗ Thiện Lĩnh — Frontend, Backend, Infrastructure & K8s
- Name — API & Backend
- Name — Frontend & Testing

## Cấu trúc dự án

```text
.
├── backend/          FastAPI API, AI Agent và database migrations
├── frontend/         Next.js web application
├── infra/            Infrastructure configuration
├── k8s/              Kubernetes manifests và tài liệu triển khai
├── scripts/          Development và operation scripts
└── docker-compose.yml
```

## Yêu cầu

Cài đặt các công cụ sau trước khi chạy dự án:

- Docker và Docker Compose v2
- Python 3.11 trở lên
- [uv](https://docs.astral.sh/uv/)
- Node.js 22 trở lên
- pnpm
- make

## Cấu hình môi trường

Tạo file cấu hình backend:

```bash
cp backend/.env.example backend/.env
```

Điền các biến bắt buộc trong `backend/.env`, đặc biệt là thông tin PostgreSQL,
Redis, `JWT_SECRET_KEY`, `TAVILY_API_KEY` và API key của LLM.

Tạo file `frontend/.env`:

```dotenv
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api
```

Khi chạy local, sử dụng các hostname sau trong `backend/.env`:

```dotenv
POSTGRES_HOST=127.0.0.1
REDIS_HOST=127.0.0.1
```

## Quick Start

Chạy toàn bộ môi trường development bằng một lệnh:

```bash
./scripts/quick_start.sh
```

Script sẽ:

1. Khởi động PostgreSQL và Redis bằng Docker Compose.
2. Cài đặt dependencies cho backend và frontend.
3. Chạy database migrations.
4. Khởi động FastAPI và Next.js ở chế độ development.

Sau khi khởi động thành công:

- Frontend: <http://127.0.0.1:3000>
- Backend: <http://127.0.0.1:8000>
- API documentation: <http://127.0.0.1:8000/docs>

Nhấn `Ctrl+C` để dừng backend và frontend. PostgreSQL và Redis vẫn tiếp tục
chạy trong Docker.

Để dừng các dịch vụ Docker:

```bash
docker compose --env-file ./backend/.env down
```

## Chạy thủ công

Khởi động PostgreSQL và Redis:

```bash
docker compose --env-file ./backend/.env up -d database cache
```

Khởi động backend:

```bash
cd backend
make install
make db-upgrade
make run
```

Khởi động frontend trong terminal khác:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run dev
```

## Kiểm tra mã nguồn

Backend:

```bash
cd backend
make format
make lint
make check
```

Frontend:

```bash
cd frontend
pnpm run lint:check
pnpm run format:fix
pnpm run format:check
```

## Triển khai Kubernetes

Xem hướng dẫn trong [k8s/README.md](./k8s/README.md) và
[k8s/KUBERNETES_GUIDE.md](./k8s/KUBERNETES_GUIDE.md).
