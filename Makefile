.PHONY: ci lint fix typecheck security test

ci:  ## Run full CI locally (mirrors .github/workflows/ci.yml)
	@./scripts/ci-local.sh

lint:  ## Run lint checks only
	uv run ruff check .
	uv run ruff format --check .

fix:  ## Auto-fix lint issues
	uv run ruff check --fix .
	uv run ruff format .

typecheck:  ## Run mypy type checking
	uv run mypy src/

security:  ## Run bandit security scan
	uv run bandit -c pyproject.toml -r src/

test:  ## Run tests with coverage
	uv run pytest -x -q --cov --cov-fail-under=90
