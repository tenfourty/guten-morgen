# Testing Guide

## Running Tests

```bash
uv run pytest -x -q              # fast: fail on first error
uv run pytest --cov              # with coverage report
uv run pytest -k "test_name"     # run specific test
uv run pytest tests/test_models.py -v   # drift detection only
```

Tests do **not** need `MORGEN_API_KEY` — all API calls use mock transport. No network calls, no env setup required for tests.

## Test File Map

```
tests/
  conftest.py           Shared fixtures (mock transport, FAKE_* data)
  fixtures/*.json       Real API response samples (drift detection)
  test_cli_accounts.py  accounts + calendars commands
  test_cli_events.py    events list/create/update/delete
  test_cli_tasks.py     tasks CRUD, filtering, group-by-source, tags, scheduling
  test_cli_tags.py      tags CRUD
  test_cli_views.py     today/this-week/this-month combined views
  test_cli_next.py      next upcoming events
  test_cli_errors.py    parametrized error handling for all commands
  test_cli_usage.py     usage/help output
  test_cli_groups.py    calendar group filtering
  test_cli_cache.py     CLI cache flags
  test_client.py        MorgenClient methods
  test_client_tasks.py  Task-specific client methods
  test_client_cache.py  Client caching logic
  test_models.py        Pydantic model validation + API drift detection
  test_output.py        Output rendering pipeline
  test_config.py        Settings/config loading
  test_cache.py         CacheStore internals
  test_groups.py        Calendar group resolution
  test_time_utils.py    Date range helpers
```

## Mock Infrastructure

All API tests use `httpx.MockTransport` — no network calls.

### Fixture Dependencies

```mermaid
flowchart TD
    MT["mock_transport\n<i>httpx.MockTransport</i>"] --> CL["client\n<i>MorgenClient</i>"]
    CL --> MC["mock_client\n<i>patches _get_client()</i>"]
    R["runner\n<i>CliRunner</i>"]

    MC -.->|"used together"| R

    subgraph "Client tests"
        CL
    end

    subgraph "CLI tests"
        MC
        R
    end

    style MT fill:#d1ecf1,stroke:#17a2b8
    style MC fill:#d4edda,stroke:#28a745
    style R fill:#d4edda,stroke:#28a745
```

| Fixture | Type | Purpose |
|---------|------|---------|
| `runner` | `CliRunner` | Click CLI test runner |
| `client` | `MorgenClient` | Client backed by mock transport |
| `mock_client` | `MorgenClient` | Patches `_get_client()` and `load_morgen_config()` so CLI commands use the mock |

### Mock Transport Routing

```mermaid
flowchart TD
    REQ["Incoming Request"] --> EV{"/v3/events/list?"}
    EV -->|yes| ACC{"accountId param?"}
    ACC -->|acc-1| E1["FAKE_EVENTS"]
    ACC -->|acc-2| E2["FAKE_EVENTS_ACC2"]

    REQ --> TK{"/v3/tasks/list?"}
    TK -->|accountId=acc-linear| LT["FAKE_LINEAR_TASKS"]
    TK -->|accountId=acc-notion| NT["FAKE_NOTION_TASKS"]
    TK -->|no accountId| MT["FAKE_TASKS"]

    REQ --> RT{"path in ROUTES?"}
    RT -->|yes| RD["ROUTES dict\n<i>accounts, calendars, tags</i>"]

    REQ --> POST{"POST method?"}
    POST -->|yes| ECHO["Echo body in envelope\n<i>{data: {item: body}}</i>"]

    REQ --> GET{"GET with ?id="}
    GET -->|yes| SINGLE["Return fake single item"]

    REQ --> MISS["404"]

    style MISS fill:#f8d7da,stroke:#dc3545
```

Key files:
- `tests/conftest.py` — Transport handler, fake data constants (`FAKE_*`), all fixtures
- `tests/fixtures/*.json` — Real API response samples for drift detection

### Adding a new CLI test

```python
def test_my_command(self, runner: CliRunner, mock_client: MorgenClient) -> None:
    result = runner.invoke(cli, ["my-command", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    # assert on data...
```

### Adding a new client test

```python
def test_my_method(self, client: MorgenClient) -> None:
    result = client.my_method()
    assert isinstance(result, MyModel)
```

## Error Path Testing

```mermaid
flowchart LR
    P["patch.object(mock_client,\n'method',\nside_effect=Error)"] --> INV["runner.invoke(cli, args)"]
    INV --> A1["assert exit_code == 1"]
    INV --> A2["assert error JSON on output"]
    A2 --> A3["assert error.type matches"]

    style P fill:#fff3cd,stroke:#ffc107
```

Error handling uses `unittest.mock.patch` on client methods:

```python
with patch.object(mock_client, "list_accounts", side_effect=AuthenticationError("msg")):
    result = runner.invoke(cli, ["accounts", "--json"], catch_exceptions=False)
assert result.exit_code == 1
err = json.loads(result.output)
assert err["error"]["type"] == "authentication_error"
```

See `tests/test_cli_errors.py` for the full parametrized error matrix covering all commands.

## API Drift Detection

```mermaid
flowchart LR
    FIX["tests/fixtures/*.json\n<i>real API responses</i>"] --> TEST["test_models.py\n<i>parametrized</i>"]
    MOD["models.py\n<i>model fields</i>"] --> TEST
    TEST --> PASS["Pass: fields match"]
    TEST --> FAIL["Fail: new API fields\nnot in model"]

    style FAIL fill:#fff3cd,stroke:#ffc107
    style PASS fill:#d4edda,stroke:#28a745
```

To update fixtures after confirming new API fields:
1. Capture a real response: `morgen <command> --json > tests/fixtures/<model>_sample.json`
2. Add new fields to the Pydantic model in `src/morgen/models.py`
3. Run `uv run pytest tests/test_models.py -v` to verify

## Coverage

Coverage minimum is 90%, enforced by pre-commit (`--cov-fail-under=90`).

```bash
uv run pytest --cov --cov-report=term-missing    # see uncovered lines
```

Coverage exclusions (configured in `pyproject.toml`):
- `pragma: no cover` — for entrypoints like `__main__.py`
- `if TYPE_CHECKING:` — import-only blocks

When adding new features, check that new code paths have tests — especially error handling (`except MorgenError` blocks) and non-JSON output rendering.
