---
name: new-command
description: Scaffold a new CLI command with model, client method, CLI wiring, and tests following guten-morgen conventions
disable-model-invocation: true
---

# Scaffold a New guten-morgen CLI Command

Add a new resource type to the guten-morgen CLI. Argument: `$ARGUMENTS` (e.g., "reminders" or "notes").

## Prerequisites

Read these files first to understand current patterns:
- `src/guten_morgen/models.py` — existing model patterns
- `src/guten_morgen/client.py` — client method patterns
- `src/guten_morgen/cli.py` — CLI command patterns
- `tests/conftest.py` — mock transport and fixtures

## Step 1: Pydantic Model

Add to `src/guten_morgen/models.py`:

```python
class NewResource(MorgenModel):
    """Description."""

    id: str
    # Add fields from the API response
    # Use `str | None = None` for optional fields
    # Use `Field(alias="weird.key")` for non-Python field names
```

Inherit from `MorgenModel` (gets `extra="ignore"` + `populate_by_name=True`).

## Step 2: Client Methods

Add to `src/guten_morgen/client.py`:

- Import the new model
- Add list/get/create/update/delete methods as needed
- Use `_extract_list(data, "key", Model)` for list endpoints
- Use `_extract_single(data, "key", Model)` for single-item endpoints
- Add caching with appropriate TTL (see `cache.py` for constants)
- GET methods: raise `NotFoundError` if result is None
- Write methods: return `T | None`, invalidate cache with `_cache_invalidate("prefix")`

## Step 3: CLI Commands

Add to `src/guten_morgen/cli.py`:

```python
# Define column and concise field lists
RESOURCE_COLUMNS = ["id", "name", ...]
RESOURCE_CONCISE_FIELDS = ["id", "name"]

@cli.group()
def resources() -> None:
    """Manage resources."""

@resources.command("list")
@output_options
def resources_list(fmt, fields, jq_expr, response_format):
    """List all resources."""
    try:
        client = _get_client()
        data = [r.model_dump() for r in client.list_resources()]
        if response_format == "concise" and not fields:
            fields = RESOURCE_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=RESOURCE_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)
```

Key patterns:
- `model_dump()` for standard resources
- `model_dump(by_alias=True)` if model has Field aliases
- `model_dump(exclude_none=True)` for mutation results (create/update)
- Always wrap in `try/except MorgenError`

## Step 4: Update `usage` Command (CRITICAL)

**This is the most important step.** `gm usage` is the LLM-facing API contract — it's the first command any AI agent runs to orient itself. If a command isn't in `usage`, it doesn't exist to the LLM.

Update the `usage()` function's docstring in `cli.py` to include:
1. The new command with all options and their descriptions
2. Usage examples in the "Scenarios" section if applicable
3. Any new global options or output fields

Match the style of existing entries exactly. Every option must be documented with its type and purpose.

## Step 5: JSON Fixture

Capture a real API response:
```bash
gm <command> --json > tests/fixtures/<resource>_sample.json
```

Or create a minimal fixture manually matching the API shape.

## Step 6: Mock Transport

In `tests/conftest.py`:
1. Add `FAKE_RESOURCES` constant with test data
2. Add route to `_handler()` function for the new endpoint
3. Handle both list and single-item patterns

## Step 7: Tests

### Drift detection (`tests/test_models.py`)
```python
def test_resource_drift(self):
    with open("tests/fixtures/resource_sample.json") as f:
        sample = json.load(f)
    # Validate model handles all fields
    Resource.model_validate(sample)
```

### CLI tests (`tests/test_cli_<resource>.py`)
```python
class TestResourceCommands:
    def test_list_json(self, runner, mock_client):
        result = runner.invoke(cli, ["resources", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_list_table(self, runner, mock_client):
        result = runner.invoke(cli, ["resources", "list"])
        assert result.exit_code == 0
```

### Error tests (`tests/test_cli_errors.py`)
Add to the parametrized error matrix:
```python
("resources list --json", "list_resources"),
```

### Client tests (`tests/test_client.py` or new file)
```python
def test_list_resources(self, client):
    result = client.list_resources()
    assert isinstance(result, list)
    assert all(isinstance(r, Resource) for r in result)
```

## Step 8: Verify

```bash
uv run pytest -x -q --cov
uv run mypy src/
```

Both must pass. Coverage must stay >= 90%.

## Step 9: Update CLAUDE.md

If the new resource adds a file not in the file map, update `CLAUDE.md`.
