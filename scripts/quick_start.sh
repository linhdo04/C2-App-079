#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

backend_pid=""
frontend_pid=""

cleanup() {
  trap - INT TERM EXIT

  [[ -z "$backend_pid" ]] || kill "$backend_pid" 2>/dev/null || true
  [[ -z "$frontend_pid" ]] || kill "$frontend_pid" 2>/dev/null || true

  wait "$backend_pid" "$frontend_pid" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

require_command() {
  local command_name="$1"

  command -v "$command_name" >/dev/null 2>&1 || {
    echo "$command_name is required but was not found." >&2
    exit 1
  }
}

require_command docker
require_command make
require_command pnpm
require_command uv

docker info >/dev/null 2>&1 || {
  echo "Docker is installed, but the Docker daemon is not running." >&2
  exit 1
}

docker compose version >/dev/null 2>&1 || {
  echo "Docker Compose v2 is required (the 'docker compose' command)." >&2
  exit 1
}

[[ -f "$PROJECT_DIR/backend/.env" ]] || {
  echo "Missing backend/.env. Copy backend/.env.example and configure it first." >&2
  exit 1
}

[[ -f "$PROJECT_DIR/frontend/.env" ]] || {
  echo "Missing frontend/.env. Create it with NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api." >&2
  exit 1
}

echo "Starting PostgreSQL and Redis..."
docker compose \
  --env-file "$PROJECT_DIR/backend/.env" \
  -f "$PROJECT_DIR/docker-compose.yml" \
  up -d database cache

echo "Installing backend dependencies..."
make -C "$PROJECT_DIR/backend" install

echo "Installing frontend dependencies..."
pnpm --dir "$PROJECT_DIR/frontend" install --frozen-lockfile

echo "Applying database migrations..."
make -C "$PROJECT_DIR/backend" db-upgrade

echo "Starting backend and frontend..."
(cd "$PROJECT_DIR/backend" && make run) &
backend_pid=$!

(cd "$PROJECT_DIR/frontend" && pnpm run dev) &
frontend_pid=$!

echo
echo "Project is running:"
echo "  Frontend: http://127.0.0.1:3000"
echo "  Backend:  http://127.0.0.1:8000"
echo "  API docs: http://127.0.0.1:8000/docs"
echo
echo "Press Ctrl+C to stop the development servers."
echo "PostgreSQL and Redis will continue running in Docker."

while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 1
done

echo "A development server stopped unexpectedly." >&2
exit 1
