.PHONY: help install update lint format typecheck test eval eval-worker eval-orchestrator check experiments

help:
	@echo "Available commands:"
	@echo "  make install           - Install exact locked dependencies (reproducible)"
	@echo "  make update            - Update dependencies to latest compatible versions"
	@echo "  make lint              - Run ruff linter"
	@echo "  make format            - Run ruff formatter and auto-fix linter issues"
	@echo "  make typecheck         - Run mypy type checker"
	@echo "  make test              - Run pytest test suite (offline deterministic tests)"
	@echo "  make eval              - Run full evaluations suite with pytest"
	@echo "  make eval-worker       - Run Worker agent evaluations directly"
	@echo "  make eval-orchestrator - Run Orchestrator agent evaluations directly"
	@echo "  make experiments       - Run multi-scenario prompt injection experiments"
	@echo "  make check             - Run all quality checks (lint, typecheck, test)"

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

eval:
	uv run pytest evals/

eval-worker:
	uv run python -m evals.test_eval_worker

eval-orchestrator:
	uv run python -m evals.test_eval_orchestrator

experiments:
	uv run python -m experiments.run_experiments

check: lint typecheck test
