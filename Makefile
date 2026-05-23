.PHONY: install lock lint lint-fix format format-check typecheck test check migrate downgrade compose-up compose-down compose-logs playground clean

install:
	uv sync

lock:
	uv lock

lint:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run mypy .

test:
	uv run pytest

check: lint format-check typecheck test

migrate:
	uv run alembic upgrade head

downgrade:
	uv run alembic downgrade base

compose-up:
	docker compose up

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f

playground:
	uv run adk web .

clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache htmlcov .coverage build dist
