.DEFAULT_GOAL := help

.PHONY: help run test lint lint-check format format-check typecheck check db-migrate db-upgrade db-downgrade db-seed agent-prompts-sync sync-prompts

help:
	@echo ""
	@echo "Available commands:"
	@echo ""
	@echo "  make install           Install dependencies"
	@echo "  make setup             Install dependencies + pre-commit hooks"
	@echo "  make run               Start the FastAPI development server"
	@echo "  make test              Run tests"
	@echo "  make lint-check        Check code style with Ruff"
	@echo "  make lint              Fix lint issues with Ruff"
	@echo "  make format            Format code with Ruff"
	@echo "  make format-check      Check code formatting"
	@echo "  make typecheck         Run MyPy type checking"
	@echo "  make check             Run all checks (lint, format, typecheck, test)"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate m='migration_name'"
	@echo "                         Create a new Alembic migration"
	@echo "  make db-upgrade        Apply all pending migrations"
	@echo "  make db-downgrade      Roll back the latest migration"
	@echo "  make db-seed           Seed demo user, mission, sensor and telemetry"
	@echo "  make agent-prompts-sync args='--dry-run'"
	@echo "                         Sync local agent prompts to LangSmith"
	@echo ""

install:
	uv sync --all-extras

setup:
	uv sync --all-extras && pre-commit install

run:
	uv run uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	LANGSMITH_TRACING=false uv run pytest

lint-check:
	uv run ruff check .

lint:
	uv run ruff check . --fix

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy .

check: lint-check format-check typecheck test

db-migrate:
	@if [ -z "$(m)" ]; then \
		echo "Error: Migration name is required. Example: make db-migrate m='add_new_table'"; \
		exit 1; \
	fi
	uv run alembic revision --autogenerate -m "$(m)"

db-upgrade:
	uv run alembic upgrade head

db-downgrade:
	uv run alembic downgrade -1

db-seed:
	uv run python -m scripts.seed_demo

agent-prompts-sync:
	uv run python -m scripts.sync_prompts $(args)

sync-prompts: agent-prompts-sync
