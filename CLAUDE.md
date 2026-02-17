# morgen CLI

Calendar and task management CLI for the Morgen API, optimised for LLM consumption.

## Development

```bash
uv sync --all-extras          # Install all deps
uv run pre-commit install     # Install pre-commit hooks (ruff, mypy, pytest)
uv run pytest                 # Run tests
uv run mypy src/              # Type check
uv run ruff check .           # Lint
uv run morgen usage           # Self-documentation
```

**After cloning**, always run `uv sync --all-extras && uv run pre-commit install` to set up the environment.

## TDD Workflow

1. Write failing test in `tests/`
2. Implement in `src/morgen/`
3. `uv run pytest` — green
4. `uv run mypy src/ && uv run ruff check .` — clean

## Architecture

- `cli.py` — Click commands with `@output_options` decorator
- `client.py` — `MorgenClient` typed httpx wrapper
- `config.py` — Settings from `.env`
- `models.py` — TypedDict definitions
- `output.py` — Render pipeline (table/json/jsonl/csv + fields + jq)
- `errors.py` — Exception hierarchy + structured errors
- `time_utils.py` — Date range helpers

## Conventions

- `from __future__ import annotations` in every file
- All files typed, mypy strict
- Tests use `httpx.MockTransport` and `click.testing.CliRunner`
