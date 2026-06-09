.DEFAULT_GOAL := help

.PHONY: help run test lint lint-check format format-check typecheck check db-migrate db-upgrade db-downgrade

help:
	@echo ""
	@echo "Available commands:"
	@echo ""
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
	@echo ""

run:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest

lint-check:
	ruff check .

lint:
	ruff check . --fix

format:
	ruff format .

format-check:
	ruff format --check .

typecheck:
	mypy .

check: lint-check format-check typecheck test

db-migrate:
	@if [ -z "$(m)" ]; then \
		echo "Error: Migration name is required. Example: make db-migrate m='add_new_table'"; \
		exit 1; \
	fi
	alembic revision --autogenerate -m "$(m)"

db-upgrade:
	alembic upgrade head

db-downgrade:
	alembic downgrade -1
