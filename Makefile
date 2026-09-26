.PHONY: run test lint typecheck eval quality

run:
	uv run uvicorn polaris_guidance.app:app --reload --port 8080

test:
	uv run coverage run -m pytest -q
	uv run coverage report

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy

eval:
	uv run python evals/run_evals.py

quality: lint typecheck test eval

