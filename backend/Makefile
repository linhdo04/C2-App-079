.PHONY: run test lint format format-check typecheck check

run:
	uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format --check .

typecheck:
	mypy .

check: lint format-check typecheck test
