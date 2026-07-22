.PHONY: fix lint format test run up down

fix:
	uv run ruff check . --fix
	uv run ruff format .

lint:
	uv run ruff check .

format:
	uv run ruff format .

test:
	uv run pytest

run:
	uv run uvicorn vektor.main:app --reload

up:
	docker compose up -d

down:
	docker compose down
