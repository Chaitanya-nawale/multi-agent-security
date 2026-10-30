.PHONY: help install update lint format typecheck test check

help:
	@echo "Available commands:"
	@echo "  make install    - Install exact locked dependencies (reproducible)"
	@echo "  make update     - Update dependencies to latest compatible versions"
	@echo "  make lint       - Run ruff linter"
	@echo "  make format     - Run ruff formatter and auto-fix linter issues"
	@echo "  make typecheck  - Run mypy type checker"
	@echo "  make test       - Run pytest test suite"
	@echo "  make check      - Run all quality checks (lint, typecheck, test)"

install:
	uv sync --frozen

update:
	uv lock --upgrade
	uv sync


lint:
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy .

test:
	uv run pytest

check: lint typecheck test
