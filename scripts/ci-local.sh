#!/bin/bash
# Local CI mirror — runs the same steps as .github/workflows/ci.yml
# Usage: ./scripts/ci-local.sh [--fix]
#   --fix: auto-fix lint issues instead of just checking

set -e

FIX=0
if [[ "$1" == "--fix" ]]; then
  FIX=1
fi

echo "=== Install dependencies ==="
uv sync --all-extras

echo ""
echo "=== Lint ==="
if [[ $FIX -eq 1 ]]; then
  uv run ruff check --fix .
  uv run ruff format .
  echo "(auto-fixed)"
else
  uv run ruff check .
  uv run ruff format --check .
fi

echo ""
echo "=== Type check ==="
uv run mypy src/

echo ""
echo "=== Security scan ==="
uv run bandit -c pyproject.toml -r src/

echo ""
echo "=== Test ==="
uv run pytest -x -q --cov --cov-fail-under=90

echo ""
echo "=== All checks passed ==="
