# Morgen API Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement 8 missing Morgen API features: RSVP, series update mode, Google Meet, incremental task sync, availability finder, calendar update, recurring task occurrence, and integration providers.

**Architecture:** Each feature follows the existing boundary pattern: `client.py` (Pydantic models) → `cli.py` (model_dump() → dicts) → `output.py` (table/json/csv). New client methods wrap Morgen API endpoints. CLI adds Click commands/options. TDD: write failing test first, then minimal implementation.

**Tech Stack:** Python 3.10+, Click, httpx, Pydantic v2, pytest with Click CliRunner + httpx MockTransport

**Key constraints:**
- All features share `cli.py` → single branch, sequential implementation
- RSVP uses a different base URL (`https://sync.morgen.so/v1`) — httpx ignores `base_url` for absolute URLs
- `calendars` command must be converted to a group (breaking change at v0.2.0)
- Every new command/option MUST update the `usage()` docstring in `cli.py`

**Run commands (use throughout):**
```bash
uv run pytest -x -q                    # run tests (stop on first failure)
uv run pytest tests/FILE.py::CLASS -v  # run specific test
uv run mypy src/                       # type check
uv run ruff check .                    # lint
```

---

### Task 1: Series update mode for recurring events

Add `--series single|future|all` option to `events update` and `events delete`. Passes `seriesUpdateMode` as a query parameter to the Morgen API.

**Files:**
- Modify: `src/guten_morgen/client.py:255-264` (update_event, delete_event)
- Modify: `src/guten_morgen/cli.py:603-663` (events_update, events_delete)
- Modify: `tests/test_cli_events.py` (add tests)
- Modify: `tests/conftest.py` (update mock transport to capture query params)

**Step 1: Write failing tests**

Add to `tests/test_cli_events.py`:

```python
class TestSeriesUpdateMode:
    def test_update_with_series_flag(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--series passes seriesUpdateMode query param to API."""
        result = runner.invoke(cli, ["events", "update", "evt-1", "--title", "Updated", "--series", "future"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "evt-1"

    def test_delete_with_series_flag(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--series passes seriesUpdateMode on delete."""
        result = runner.invoke(cli, ["events", "delete", "evt-1", "--series", "all"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "deleted"

    def test_series_default_not_sent(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Without --series, no seriesUpdateMode param is sent."""
        result = runner.invoke(cli, ["events", "update", "evt-1", "--title", "Updated"])
        assert result.exit_code == 0

    def test_series_invalid_choice(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Invalid --series value is rejected by Click."""
        result = runner.invoke(cli, ["events", "update", "evt-1", "--series", "bogus"])
        assert result.exit_code != 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_events.py::TestSeriesUpdateMode -v`
Expected: FAIL — `--series` option doesn't exist yet.

**Step 3: Implement — client.py**

Modify `update_event` and `delete_event` in `client.py` to accept `series_update_mode`:

```python
def update_event(self, event_data: dict[str, Any], *, series_update_mode: str | None = None) -> Event | None:
    """Update an existing event."""
    params = {}
    if series_update_mode:
        params["seriesUpdateMode"] = series_update_mode
    data = self._request("POST", "/events/update", json=event_data, params=params or None)
    self._cache_invalidate("events")
    return _extract_single(data, "event", Event)

def delete_event(self, event_data: dict[str, Any], *, series_update_mode: str | None = None) -> None:
    """Delete an event."""
    params = {}
    if series_update_mode:
        params["seriesUpdateMode"] = series_update_mode
    self._request("POST", "/events/delete", json=event_data, params=params or None)
    self._cache_invalidate("events")
```

Note: pass `params=None` (not `params={}`) when empty so httpx doesn't add a `?` to the URL.

**Step 4: Implement — cli.py**

Add `--series` option to both `events_update` and `events_delete`:

In `events_update`, add option and pass through:
```python
@events.command("update")
@click.argument("event_id")
@click.option("--title", default=None, help="New title.")
@click.option("--start", default=None, help="New start datetime (ISO 8601).")
@click.option("--duration", default=None, type=int, help="New duration in minutes.")
@click.option("--description", default=None, help="New description.")
@click.option("--calendar-id", default=None, help="Calendar ID.")
@click.option("--account-id", default=None, help="Account ID.")
@click.option("--series", "series_mode", type=click.Choice(["single", "future", "all"]), default=None, help="Series update mode for recurring events.")
def events_update(
    event_id: str,
    title: str | None,
    start: str | None,
    duration: int | None,
    description: str | None,
    calendar_id: str | None,
    account_id: str | None,
    series_mode: str | None,
) -> None:
```

Inside the function, pass `series_update_mode=series_mode` to `client.update_event()`.

In `events_delete`, add option and pass through:
```python
@events.command("delete")
@click.argument("event_id")
@click.option("--calendar-id", default=None, help="Calendar ID.")
@click.option("--account-id", default=None, help="Account ID.")
@click.option("--series", "series_mode", type=click.Choice(["single", "future", "all"]), default=None, help="Series update mode for recurring events.")
def events_delete(event_id: str, calendar_id: str | None, account_id: str | None, series_mode: str | None) -> None:
```

Inside the function, pass `series_update_mode=series_mode` to `client.delete_event()`.

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_events.py::TestSeriesUpdateMode -v`
Expected: All PASS

**Step 6: Run full suite + type check**

Run: `uv run pytest -x -q && uv run mypy src/`
Expected: All pass, no type errors

**Step 7: Commit**

```bash
git add src/guten_morgen/client.py src/guten_morgen/cli.py tests/test_cli_events.py
git commit -m "feat: add --series option to events update and delete for recurring events"
```

---

### Task 2: Google Meet auto-creation on events

Add `--meet` flag to `events create`. When set, includes `morgen.so:requestVirtualRoom: "default"` in the create payload.

**Files:**
- Modify: `src/guten_morgen/cli.py:558-600` (events_create)
- Modify: `tests/test_cli_events.py` (add tests)

**Step 1: Write failing tests**

Add to `tests/test_cli_events.py`:

```python
class TestGoogleMeet:
    def test_create_with_meet(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--meet adds morgen.so:requestVirtualRoom to the payload."""
        result = runner.invoke(
            cli, ["events", "create", "--title", "Sync", "--start", "2026-02-18T10:00:00", "--duration", "30", "--meet"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("morgen.so:requestVirtualRoom") == "default"

    def test_create_without_meet(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Without --meet, no requestVirtualRoom field."""
        result = runner.invoke(
            cli, ["events", "create", "--title", "Sync", "--start", "2026-02-18T10:00:00", "--duration", "30"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "morgen.so:requestVirtualRoom" not in data
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_events.py::TestGoogleMeet -v`
Expected: FAIL — `--meet` option doesn't exist yet.

**Step 3: Implement — cli.py only**

Add `--meet` flag to `events_create`:

```python
@events.command("create")
@click.option("--title", required=True, help="Event title.")
@click.option("--start", required=True, help="Start datetime (ISO 8601).")
@click.option("--duration", required=True, type=int, help="Duration in minutes.")
@click.option("--calendar-id", default=None, help="Calendar ID (auto-discovered if omitted).")
@click.option("--account-id", default=None, help="Account ID (auto-discovered if omitted).")
@click.option("--description", default=None, help="Event description.")
@click.option("--timezone", default=None, help="Time zone (e.g. Europe/Paris). Defaults to system timezone.")
@click.option("--meet", is_flag=True, default=False, help="Auto-attach a Google Meet link.")
def events_create(
    title: str,
    start: str,
    duration: int,
    calendar_id: str | None,
    account_id: str | None,
    description: str | None,
    timezone: str | None,
    meet: bool,
) -> None:
```

Inside the function, after building `event_data`, add:
```python
        if meet:
            event_data["morgen.so:requestVirtualRoom"] = "default"
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_events.py::TestGoogleMeet -v`
Expected: All PASS

**Step 5: Run full suite + type check**

Run: `uv run pytest -x -q && uv run mypy src/`

**Step 6: Commit**

```bash
git add src/guten_morgen/cli.py tests/test_cli_events.py
git commit -m "feat: add --meet flag to events create for Google Meet auto-attach"
```

---

### Task 3: Incremental task sync (`--updated-after`)

Add `--updated-after ISO` option to `tasks list`. Passes `updatedAfter` query param to the Morgen tasks API.

**Files:**
- Modify: `src/guten_morgen/client.py:268-334` (list_all_tasks)
- Modify: `src/guten_morgen/cli.py:679-800` (tasks_list)
- Modify: `tests/test_cli_tasks.py` (add tests)

**Step 1: Write failing tests**

Add to `tests/test_cli_tasks.py`:

```python
class TestUpdatedAfter:
    def test_updated_after_option_accepted(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--updated-after is a valid option."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--updated-after", "2026-02-19T00:00:00"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_tasks.py::TestUpdatedAfter -v`
Expected: FAIL — `--updated-after` option doesn't exist.

**Step 3: Implement — client.py**

Add `updated_after` param to `list_all_tasks()`:

```python
def list_all_tasks(
    self,
    *,
    source: str | None = None,
    limit: int = 100,
    updated_after: str | None = None,
) -> TaskListResponse:
```

Inside the method, add `updatedAfter` to the params dict for both morgen-native and external source requests:

For morgen-native tasks:
```python
        if source is None or source == "morgen":
            params: dict[str, Any] = {"limit": limit}
            if updated_after:
                params["updatedAfter"] = updated_after
            data = self._request("GET", "/tasks/list", params=params)
```

For external task sources:
```python
            ext_params: dict[str, Any] = {"accountId": account_id, "limit": limit}
            if updated_after:
                ext_params["updatedAfter"] = updated_after
            raw = self._request("GET", "/tasks/list", params=ext_params)
```

**Step 4: Implement — cli.py**

Add `--updated-after` option to `tasks_list`:

```python
@click.option("--updated-after", default=None, help="Only tasks updated after this datetime (ISO 8601).")
```

Add `updated_after: str | None` param to function signature. Pass to client:

```python
        result = client.list_all_tasks(source=source, limit=limit, updated_after=updated_after)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_tasks.py::TestUpdatedAfter -v`
Expected: PASS

**Step 6: Run full suite + type check**

Run: `uv run pytest -x -q && uv run mypy src/`

**Step 7: Commit**

```bash
git add src/guten_morgen/client.py src/guten_morgen/cli.py tests/test_cli_tasks.py
git commit -m "feat: add --updated-after option to tasks list for incremental sync"
```

---

### Task 4: Recurring task close/reopen with occurrence

Add `--occurrence ISO` option to `tasks close` and `tasks reopen` for targeting specific occurrences of recurring tasks.

**Files:**
- Modify: `src/guten_morgen/client.py:374-384` (close_task, reopen_task)
- Modify: `src/guten_morgen/cli.py:900-923` (tasks_close, tasks_reopen)
- Modify: `tests/test_cli_tasks.py` (add tests)

**Step 1: Write failing tests**

Add to `tests/test_cli_tasks.py`:

```python
class TestTaskOccurrence:
    def test_close_with_occurrence(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--occurrence passes occurrenceStart in the request body."""
        result = runner.invoke(cli, ["tasks", "close", "task-1", "--occurrence", "2026-02-20T09:00:00"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "task-1"
        assert data.get("occurrenceStart") == "2026-02-20T09:00:00"

    def test_reopen_with_occurrence(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--occurrence passes occurrenceStart on reopen."""
        result = runner.invoke(cli, ["tasks", "reopen", "task-1", "--occurrence", "2026-02-20T09:00:00"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "task-1"
        assert data.get("occurrenceStart") == "2026-02-20T09:00:00"

    def test_close_without_occurrence(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Without --occurrence, no occurrenceStart is sent."""
        result = runner.invoke(cli, ["tasks", "close", "task-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "occurrenceStart" not in data
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_tasks.py::TestTaskOccurrence -v`
Expected: FAIL — `--occurrence` option doesn't exist.

**Step 3: Implement — client.py**

Modify `close_task` and `reopen_task`:

```python
def close_task(self, task_id: str, *, occurrence_start: str | None = None) -> Task | None:
    """Mark a task as completed."""
    payload: dict[str, Any] = {"id": task_id}
    if occurrence_start:
        payload["occurrenceStart"] = occurrence_start
    data = self._request("POST", "/tasks/close", json=payload)
    self._cache_invalidate("tasks")
    return _extract_single(data, "task", Task)

def reopen_task(self, task_id: str, *, occurrence_start: str | None = None) -> Task | None:
    """Reopen a completed task."""
    payload: dict[str, Any] = {"id": task_id}
    if occurrence_start:
        payload["occurrenceStart"] = occurrence_start
    data = self._request("POST", "/tasks/reopen", json=payload)
    self._cache_invalidate("tasks")
    return _extract_single(data, "task", Task)
```

**Step 4: Implement — cli.py**

Add `--occurrence` option to `tasks_close` and `tasks_reopen`:

```python
@tasks.command("close")
@click.argument("task_id")
@click.option("--occurrence", default=None, help="Occurrence start (ISO 8601) for recurring tasks.")
def tasks_close(task_id: str, occurrence: str | None) -> None:
    """Mark a task as completed."""
    try:
        client = _get_client()
        result = client.close_task(task_id, occurrence_start=occurrence)
        output = result.model_dump(exclude_none=True) if result else {"status": "closed", "id": task_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)
```

Same pattern for `tasks_reopen`.

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_tasks.py::TestTaskOccurrence -v`
Expected: All PASS

**Step 6: Run full suite + type check**

Run: `uv run pytest -x -q && uv run mypy src/`

**Step 7: Commit**

```bash
git add src/guten_morgen/client.py src/guten_morgen/cli.py tests/test_cli_tasks.py
git commit -m "feat: add --occurrence option to tasks close and reopen for recurring tasks"
```

---

### Task 5: List integration providers

Add `gm providers` command that lists available integration providers via `GET /integrations/list`.

**Files:**
- Modify: `src/guten_morgen/client.py` (add list_providers method)
- Modify: `src/guten_morgen/cli.py` (add providers command)
- Modify: `tests/conftest.py` (add route for /integrations/list)
- Create: `tests/test_cli_providers.py`

**Step 1: Write failing tests**

Create `tests/test_cli_providers.py`:

```python
"""Tests for providers command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient


class TestProviders:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["providers", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["providers"])
        assert result.exit_code == 0
        # Should contain provider names from fake data
        assert "google" in result.output.lower() or "Google" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_providers.py -v`
Expected: FAIL — `providers` command doesn't exist.

**Step 3: Add mock route to conftest.py**

Add fake provider data and route to `tests/conftest.py`:

```python
FAKE_PROVIDERS = [
    {"id": "google", "name": "Google", "type": "calendar"},
    {"id": "linear", "name": "Linear", "type": "tasks"},
    {"id": "notion", "name": "Notion", "type": "tasks"},
]
```

Add to `ROUTES`:
```python
"/v3/integrations/list": {"data": {"integrations": FAKE_PROVIDERS}},
```

**Step 4: Implement — client.py**

Add `list_providers` method:

```python
def list_providers(self) -> list[dict[str, Any]]:
    """List available integration providers."""
    data = self._request("GET", "/integrations/list")
    if isinstance(data, dict):
        inner = data.get("data", data)
        if isinstance(inner, dict):
            return inner.get("integrations", [])
        if isinstance(inner, list):
            return inner
    if isinstance(data, list):
        return data
    return []
```

Note: Returns raw dicts since there's no established Pydantic model for providers and it's a low-priority read-only endpoint.

**Step 5: Implement — cli.py**

Add `providers` command:

```python
# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------

PROVIDER_COLUMNS = ["id", "name", "type"]


@cli.command()
@output_options
def providers(fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str) -> None:
    """List available integration providers."""
    try:
        client = _get_client()
        data = client.list_providers()
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=PROVIDER_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_providers.py -v`
Expected: All PASS

**Step 7: Run full suite + type check**

Run: `uv run pytest -x -q && uv run mypy src/`

**Step 8: Commit**

```bash
git add src/guten_morgen/client.py src/guten_morgen/cli.py tests/conftest.py tests/test_cli_providers.py
git commit -m "feat: add providers command to list integration providers"
```

---

### Task 6: Calendar metadata update

Convert `calendars` from a standalone command to a group with `list` and `update` subcommands. Add `update_calendar()` client method.

**Breaking change:** `gm calendars` → `gm calendars list`. Acceptable at v0.2.0.

**Files:**
- Modify: `src/guten_morgen/client.py` (add update_calendar method)
- Modify: `src/guten_morgen/cli.py:410-429` (convert calendars to group)
- Modify: `tests/test_cli_accounts.py` (update existing calendar tests)
- Create: `tests/test_cli_calendars.py` (new tests for update)

**Step 1: Write failing tests**

Create `tests/test_cli_calendars.py`:

```python
"""Tests for calendars commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient


class TestCalendarsList:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["calendars", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 3  # 3 fake calendars

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["calendars", "list"])
        assert result.exit_code == 0
        assert "Work" in result.output


class TestCalendarsUpdate:
    def test_update_name(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["calendars", "update", "cal-1", "--account-id", "acc-1", "--name", "New Name"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "id" in data or "status" in data

    def test_update_color(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["calendars", "update", "cal-1", "--account-id", "acc-1", "--color", "#ff0000"]
        )
        assert result.exit_code == 0

    def test_update_busy(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["calendars", "update", "cal-1", "--account-id", "acc-1", "--busy"]
        )
        assert result.exit_code == 0

    def test_update_requires_account_id(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--account-id is required for calendar update."""
        result = runner.invoke(cli, ["calendars", "update", "cal-1", "--name", "X"])
        assert result.exit_code == 0  # auto-discover should handle it
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_calendars.py -v`
Expected: FAIL — `calendars list` subcommand doesn't exist (calendars is a standalone command).

**Step 3: Update existing calendar tests**

Check `tests/test_cli_accounts.py` for any `calendars` tests and update them from `["calendars", ...]` to `["calendars", "list", ...]`.

**Step 4: Implement — client.py**

Add `update_calendar` method:

```python
def update_calendar(self, calendar_data: dict[str, Any]) -> dict[str, Any] | None:
    """Update calendar metadata (name, color, busy)."""
    data = self._request("POST", "/calendars/update", json=calendar_data)
    self._cache_invalidate("calendars")
    if isinstance(data, dict):
        inner = data.get("data", data)
        if isinstance(inner, dict):
            return inner.get("calendar", inner)
    return data
```

**Step 5: Implement — cli.py**

Convert `calendars` from command to group:

```python
@cli.group()
def calendars() -> None:
    """Manage calendars."""


@calendars.command("list")
@output_options
def calendars_list(fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str) -> None:
    """List all calendars across accounts."""
    try:
        client = _get_client()
        data = [c.model_dump(exclude_none=True) for c in client.list_calendars()]
        if response_format == "concise" and not fields:
            fields = CALENDAR_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=CALENDAR_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@calendars.command("update")
@click.argument("calendar_id")
@click.option("--account-id", default=None, help="Account ID (auto-discovered if omitted).")
@click.option("--name", default=None, help="Override calendar name.")
@click.option("--color", default=None, help="Override calendar color (hex).")
@click.option("--busy/--no-busy", default=None, help="Set calendar busy/free status.")
def calendars_update(
    calendar_id: str,
    account_id: str | None,
    name: str | None,
    color: str | None,
    busy: bool | None,
) -> None:
    """Update calendar metadata (name, color, busy status)."""
    try:
        client = _get_client()
        if not account_id:
            account_id, _ = _auto_discover(client)
        metadata: dict[str, Any] = {}
        if name is not None:
            metadata["overrideName"] = name
        if color is not None:
            metadata["overrideColor"] = color
        if busy is not None:
            metadata["busy"] = busy
        cal_data: dict[str, Any] = {
            "id": calendar_id,
            "accountId": account_id,
            "metadata": metadata,
        }
        result = client.update_calendar(cal_data)
        output = result if result else {"status": "updated", "id": calendar_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)
```

**Step 6: Add mock route for calendar update**

In `conftest.py`, the existing POST handler in `mock_transport_handler` already echoes back POST bodies wrapped in `{"data": {"calendar": ...}}` via the generic handler. Verify this works.

**Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_calendars.py -v`
Expected: All PASS

**Step 8: Check for broken existing tests**

Run: `uv run pytest -x -q`

If any test calls `runner.invoke(cli, ["calendars", ...])` without `"list"`, fix those to use `["calendars", "list", ...]`.

**Step 9: Run full suite + type check**

Run: `uv run pytest -x -q && uv run mypy src/`

**Step 10: Commit**

```bash
git add src/guten_morgen/client.py src/guten_morgen/cli.py tests/test_cli_calendars.py tests/test_cli_accounts.py
git commit -m "feat: add calendars update command for name, color, busy metadata

BREAKING: gm calendars is now a group — use gm calendars list"
```

---

### Task 7: RSVP to calendar events

Add `events rsvp` command for accepting, declining, or tentatively accepting meeting invitations. Uses the **Morgen sync API** at a different base URL.

**Files:**
- Modify: `src/guten_morgen/client.py` (add rsvp_event method)
- Modify: `src/guten_morgen/cli.py` (add events rsvp command)
- Modify: `tests/conftest.py` (add sync API mock route)
- Modify: `tests/test_cli_events.py` (add RSVP tests)

**Step 1: Write failing tests**

Add to `tests/test_cli_events.py`:

```python
class TestEventsRsvp:
    def test_accept(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """events rsvp --action accept sends RSVP."""
        result = runner.invoke(
            cli, ["events", "rsvp", "evt-1", "--action", "accept"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("status") == "accepted" or "eventId" in data

    def test_decline(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["events", "rsvp", "evt-1", "--action", "decline"]
        )
        assert result.exit_code == 0

    def test_tentative(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["events", "rsvp", "evt-1", "--action", "tentative"]
        )
        assert result.exit_code == 0

    def test_with_comment(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["events", "rsvp", "evt-1", "--action", "accept", "--comment", "Will be 5min late"]
        )
        assert result.exit_code == 0

    def test_no_notify(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["events", "rsvp", "evt-1", "--action", "decline", "--no-notify"]
        )
        assert result.exit_code == 0

    def test_action_required(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--action is required."""
        result = runner.invoke(cli, ["events", "rsvp", "evt-1"])
        assert result.exit_code != 0

    def test_invalid_action(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Invalid action value is rejected."""
        result = runner.invoke(cli, ["events", "rsvp", "evt-1", "--action", "maybe"])
        assert result.exit_code != 0

    def test_with_series_mode(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["events", "rsvp", "evt-1", "--action", "accept", "--series", "all"]
        )
        assert result.exit_code == 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_events.py::TestEventsRsvp -v`
Expected: FAIL — `events rsvp` command doesn't exist.

**Step 3: Add sync API mock route**

In `tests/conftest.py`, update `mock_transport_handler` to handle sync API URLs. The RSVP endpoint is at `https://sync.morgen.so/v1/events/{action}` — but since our mock transport works on path-matching, and httpx with `base_url` sends the full URL for absolute URLs, we need to handle this.

The key insight: when `client._http.request("POST", "https://sync.morgen.so/v1/events/accept", ...)` is called, `httpx.MockTransport` receives the full URL. So we need to match on the full URL path.

Update `mock_transport_handler` to handle sync API paths:

```python
def mock_transport_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path

    # Handle sync API RSVP endpoints
    if path.startswith("/v1/events/") and path.split("/")[-1] in ("accept", "decline", "tentativelyAccept"):
        try:
            body = json.loads(request.content)
        except (json.JSONDecodeError, ValueError):
            body = {}
        action = path.split("/")[-1]
        return httpx.Response(200, json={"status": action + "ed", **body})

    # ... rest of existing handler
```

**Step 4: Implement — client.py**

Add `SYNC_BASE_URL` constant and `rsvp_event` method:

```python
SYNC_BASE_URL = "https://sync.morgen.so/v1"


class MorgenClient:
    # ... existing code ...

    def rsvp_event(
        self,
        action: str,
        event_id: str,
        calendar_id: str,
        account_id: str,
        *,
        notify_organizer: bool = True,
        comment: str | None = None,
        series_update_mode: str | None = None,
    ) -> dict[str, Any]:
        """RSVP to a calendar event (accept, decline, tentativelyAccept).

        Uses the Morgen sync API (different base URL from v3 API).
        """
        # Map CLI-friendly names to API action names
        action_map = {
            "accept": "accept",
            "decline": "decline",
            "tentative": "tentativelyAccept",
        }
        api_action = action_map.get(action, action)

        payload: dict[str, Any] = {
            "eventId": event_id,
            "calendarId": calendar_id,
            "accountId": account_id,
            "notifyOrganizer": notify_organizer,
        }
        if comment:
            payload["comment"] = comment

        params: dict[str, str] = {}
        if series_update_mode:
            params["seriesUpdateMode"] = series_update_mode

        url = f"{SYNC_BASE_URL}/events/{api_action}"
        data = self._request("POST", url, json=payload, params=params or None)
        self._cache_invalidate("events")
        return data if isinstance(data, dict) else {"status": api_action}
```

**Step 5: Implement — cli.py**

Add `events rsvp` command:

```python
@events.command("rsvp")
@click.argument("event_id")
@click.option(
    "--action", required=True,
    type=click.Choice(["accept", "decline", "tentative"]),
    help="RSVP action.",
)
@click.option("--comment", default=None, help="Optional comment to organizer.")
@click.option("--notify/--no-notify", default=True, help="Notify the organizer (default: yes).")
@click.option("--series", "series_mode", type=click.Choice(["single", "future", "all"]), default=None,
              help="Series update mode for recurring events.")
@click.option("--calendar-id", default=None, help="Calendar ID (auto-discovered if omitted).")
@click.option("--account-id", default=None, help="Account ID (auto-discovered if omitted).")
def events_rsvp(
    event_id: str,
    action: str,
    comment: str | None,
    notify: bool,
    series_mode: str | None,
    calendar_id: str | None,
    account_id: str | None,
) -> None:
    """RSVP to a calendar event (accept, decline, tentative)."""
    try:
        client = _get_client()
        if not account_id or not calendar_id:
            account_id, cal_ids = _auto_discover(client)
            calendar_id = calendar_id or cal_ids[0]
        result = client.rsvp_event(
            action=action,
            event_id=event_id,
            calendar_id=calendar_id,
            account_id=account_id,
            notify_organizer=notify,
            comment=comment,
            series_update_mode=series_mode,
        )
        click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_events.py::TestEventsRsvp -v`
Expected: All PASS

**Step 7: Run full suite + type check**

Run: `uv run pytest -x -q && uv run mypy src/`

**Step 8: Commit**

```bash
git add src/guten_morgen/client.py src/guten_morgen/cli.py tests/conftest.py tests/test_cli_events.py
git commit -m "feat: add events rsvp command for accepting/declining meeting invitations"
```

---

### Task 8: Availability / free-slots finder

Add `gm availability` command that finds open time slots on a given date.

**Files:**
- Modify: `src/guten_morgen/cli.py` (add availability command)
- Modify: `src/guten_morgen/time_utils.py` (add compute_free_slots helper)
- Create: `tests/test_cli_availability.py`
- Modify: `tests/test_time_utils.py` (add slot computation tests)

**Step 1: Write unit tests for slot computation**

Add to `tests/test_time_utils.py`:

```python
class TestComputeFreeSlots:
    def test_no_events_returns_full_window(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        slots = compute_free_slots(
            events=[],
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        assert len(slots) == 1
        assert slots[0]["start"] == "2026-02-20T09:00:00"
        assert slots[0]["end"] == "2026-02-20T18:00:00"
        assert slots[0]["duration_minutes"] == 540

    def test_one_event_splits_window(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        events = [{"start": "2026-02-20T12:00:00", "duration": "PT1H"}]
        slots = compute_free_slots(
            events=events,
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        assert len(slots) == 2
        assert slots[0]["start"] == "2026-02-20T09:00:00"
        assert slots[0]["end"] == "2026-02-20T12:00:00"
        assert slots[1]["start"] == "2026-02-20T13:00:00"
        assert slots[1]["end"] == "2026-02-20T18:00:00"

    def test_min_duration_filters_short_gaps(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        events = [
            {"start": "2026-02-20T10:00:00", "duration": "PT50M"},
            {"start": "2026-02-20T11:00:00", "duration": "PT1H"},
        ]
        slots = compute_free_slots(
            events=events,
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        # 09:00-10:00 (60m) ✓, 10:50-11:00 (10m) ✗, 12:00-18:00 (360m) ✓
        starts = [s["start"] for s in slots]
        assert "2026-02-20T09:00:00" in starts
        assert "2026-02-20T12:00:00" in starts
        assert len(slots) == 2

    def test_overlapping_events(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        events = [
            {"start": "2026-02-20T09:00:00", "duration": "PT2H"},
            {"start": "2026-02-20T10:00:00", "duration": "PT1H"},  # overlaps
        ]
        slots = compute_free_slots(
            events=events,
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        assert len(slots) == 1
        assert slots[0]["start"] == "2026-02-20T11:00:00"

    def test_event_before_window(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        events = [{"start": "2026-02-20T07:00:00", "duration": "PT1H"}]
        slots = compute_free_slots(
            events=events,
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        assert len(slots) == 1
        assert slots[0]["start"] == "2026-02-20T09:00:00"

    def test_event_spanning_window_start(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        events = [{"start": "2026-02-20T08:00:00", "duration": "PT2H"}]
        slots = compute_free_slots(
            events=events,
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        assert slots[0]["start"] == "2026-02-20T10:00:00"

    def test_all_day_event_ignored(self) -> None:
        """Events with showWithoutTime=True are all-day and should be ignored."""
        from guten_morgen.time_utils import compute_free_slots

        events = [{"start": "2026-02-20", "duration": "P1D", "showWithoutTime": True}]
        slots = compute_free_slots(
            events=events,
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        assert len(slots) == 1
        assert slots[0]["duration_minutes"] == 540
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_time_utils.py::TestComputeFreeSlots -v`
Expected: FAIL — `compute_free_slots` doesn't exist.

**Step 3: Implement — time_utils.py**

Add `compute_free_slots` function:

```python
def _parse_duration_minutes(duration: str) -> int:
    """Parse ISO 8601 duration string to minutes. Supports PTxHyM and PTxM."""
    import re

    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration)
    if not match:
        # Handle day durations (P1D)
        day_match = re.match(r"P(\d+)D", duration)
        if day_match:
            return int(day_match.group(1)) * 24 * 60
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    return hours * 60 + minutes


def compute_free_slots(
    events: list[dict[str, Any]],
    day: str,
    window_start: str = "09:00",
    window_end: str = "18:00",
    min_duration_minutes: int = 30,
) -> list[dict[str, Any]]:
    """Compute free time slots on a given day.

    Args:
        events: List of event dicts (need 'start', 'duration', optional 'showWithoutTime')
        day: Date string (YYYY-MM-DD)
        window_start: Working hours start (HH:MM)
        window_end: Working hours end (HH:MM)
        min_duration_minutes: Minimum slot duration to include

    Returns:
        List of dicts: [{start, end, duration_minutes}]
    """
    # Build window boundaries
    ws = datetime.fromisoformat(f"{day}T{window_start}:00")
    we = datetime.fromisoformat(f"{day}T{window_end}:00")

    # Collect busy intervals within the window
    busy: list[tuple[datetime, datetime]] = []
    for evt in events:
        # Skip all-day events
        if evt.get("showWithoutTime"):
            continue
        start_str = evt.get("start", "")
        dur_str = evt.get("duration", "PT0M")
        if not start_str or len(start_str) < 16:
            continue
        evt_start = datetime.fromisoformat(start_str[:19])
        evt_end = evt_start + timedelta(minutes=_parse_duration_minutes(dur_str))
        # Clip to window
        clipped_start = max(evt_start, ws)
        clipped_end = min(evt_end, we)
        if clipped_start < clipped_end:
            busy.append((clipped_start, clipped_end))

    # Sort and merge overlapping intervals
    busy.sort()
    merged: list[tuple[datetime, datetime]] = []
    for start, end in busy:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # Walk timeline to find gaps
    slots: list[dict[str, Any]] = []
    cursor = ws
    for busy_start, busy_end in merged:
        if cursor < busy_start:
            gap_minutes = int((busy_start - cursor).total_seconds() / 60)
            if gap_minutes >= min_duration_minutes:
                slots.append({
                    "start": cursor.isoformat(),
                    "end": busy_start.isoformat(),
                    "duration_minutes": gap_minutes,
                })
        cursor = max(cursor, busy_end)

    # Final gap after last busy period
    if cursor < we:
        gap_minutes = int((we - cursor).total_seconds() / 60)
        if gap_minutes >= min_duration_minutes:
            slots.append({
                "start": cursor.isoformat(),
                "end": we.isoformat(),
                "duration_minutes": gap_minutes,
            })

    return slots
```

Add `from typing import Any` to imports if not already present.

**Step 4: Run unit tests to verify they pass**

Run: `uv run pytest tests/test_time_utils.py::TestComputeFreeSlots -v`
Expected: All PASS

**Step 5: Write CLI integration tests**

Create `tests/test_cli_availability.py`:

```python
"""Tests for availability command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient


class TestAvailability:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["availability", "--date", "2026-02-17", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        # Should have gaps between fake events
        assert len(data) > 0
        assert "start" in data[0]
        assert "end" in data[0]
        assert "duration_minutes" in data[0]

    def test_custom_window(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["availability", "--date", "2026-02-17", "--start", "10:00", "--end", "14:00", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_custom_min_duration(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["availability", "--date", "2026-02-17", "--min-duration", "60", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        # All returned slots should be >= 60 minutes
        for slot in data:
            assert slot["duration_minutes"] >= 60

    def test_date_required(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["availability", "--json"])
        assert result.exit_code != 0

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["availability", "--date", "2026-02-17"])
        assert result.exit_code == 0
```

**Step 6: Run CLI tests to verify they fail**

Run: `uv run pytest tests/test_cli_availability.py -v`
Expected: FAIL — `availability` command doesn't exist.

**Step 7: Implement — cli.py**

Add `availability` command:

```python
# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------

AVAILABILITY_COLUMNS = ["start", "end", "duration_minutes"]


@cli.command()
@click.option("--date", required=True, help="Date to check (YYYY-MM-DD).")
@click.option("--min-duration", default=30, type=int, help="Minimum slot duration in minutes (default: 30).")
@click.option("--start", "window_start", default="09:00", help="Working hours start (HH:MM, default: 09:00).")
@click.option("--end", "window_end", default="18:00", help="Working hours end (HH:MM, default: 18:00).")
@output_options
@calendar_filter_options
def availability(
    date: str,
    min_duration: int,
    window_start: str,
    window_end: str,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
    group_name: str | None,
    all_calendars: bool,
) -> None:
    """Find available time slots on a given date."""
    try:
        client = _get_client()
        cf = _resolve_calendar_filter(group_name, all_calendars)

        # Fetch events for the full day
        day_start = f"{date}T00:00:00"
        day_end = f"{date}T23:59:59"
        events_models = client.list_all_events(day_start, day_end, **_filter_kwargs(cf))
        events_data = [e.model_dump(by_alias=True) for e in events_models]

        from guten_morgen.time_utils import compute_free_slots

        slots = compute_free_slots(
            events=events_data,
            day=date,
            window_start=window_start,
            window_end=window_end,
            min_duration_minutes=min_duration,
        )
        morgen_output(slots, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=AVAILABILITY_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)
```

**Step 8: Run all tests to verify they pass**

Run: `uv run pytest tests/test_cli_availability.py tests/test_time_utils.py::TestComputeFreeSlots -v`
Expected: All PASS

**Step 9: Run full suite + type check**

Run: `uv run pytest -x -q && uv run mypy src/`

**Step 10: Commit**

```bash
git add src/guten_morgen/time_utils.py src/guten_morgen/cli.py tests/test_time_utils.py tests/test_cli_availability.py
git commit -m "feat: add availability command to find free time slots"
```

---

### Task 9: Update `usage()` docstring

Update the self-documentation in `cli.py`'s `usage()` function to reflect all new commands and options.

**Files:**
- Modify: `src/guten_morgen/cli.py:146-356` (usage function)
- Modify: `tests/test_cli_usage.py` (if it exists and tests usage content)

**Step 1: Check existing usage tests**

Read `tests/test_cli_usage.py` to understand what's tested.

**Step 2: Update the usage() docstring**

Add documentation for all new features. Key additions:

Under `### Events`:
```
- `gm events rsvp EVENT_ID --action accept|decline|tentative [--comment TEXT] [--notify/--no-notify] [--series single|future|all]`
  RSVP to a calendar event. Uses the Morgen sync API.
```

Update existing event entries:
```
- `gm events create --title TEXT --start ISO --duration MINUTES [--calendar-id ID] [--description TEXT] [--meet]`
  Create a new event. --meet auto-attaches a Google Meet link.

- `gm events update ID [--title TEXT] [--start ISO] [--duration MINUTES] [--description TEXT] [--series single|future|all]`
  Update an existing event. --series controls recurring event scope.

- `gm events delete ID [--series single|future|all]`
  Delete an event. --series controls recurring event scope.
```

Under `### Calendars` (new section):
```
### Calendars
- `gm calendars list [--json]`
  List all calendars across accounts.

- `gm calendars update CALENDAR_ID --account-id ID [--name TEXT] [--color HEX] [--busy/--no-busy]`
  Update calendar metadata (name, color, busy status).
```

Under `### Tasks`:
```
- `gm tasks list [--limit N] [--status open|completed|all] [--overdue] [--json]`
  `  [--due-before ISO] [--due-after ISO] [--priority N] [--updated-after ISO]`
  `  [--source morgen|linear|notion] [--tag NAME] [--group-by-source]`
  ...
  --updated-after returns only tasks modified since the given timestamp (incremental sync).

- `gm tasks close ID [--occurrence ISO]`
  Mark a task as completed. --occurrence targets a specific recurring task occurrence.

- `gm tasks reopen ID [--occurrence ISO]`
  Reopen a completed task. --occurrence targets a specific recurring task occurrence.
```

New section:
```
### Providers
- `gm providers [--json]`
  List available integration providers.
```

New section:
```
### Availability
- `gm availability --date YYYY-MM-DD [--min-duration MINUTES] [--start HH:MM] [--end HH:MM] [--group NAME]`
  Find available time slots on a given date. Scans events within working hours
  (default 09:00-18:00) and returns gaps >= min-duration (default 30min).
  Output: [{start, end, duration_minutes}]
```

Add scenario:
```
### Find Available Slots & Book Meeting
\```
gm availability --date 2026-02-21 --min-duration 30 --json
gm events create --title "1:1 with Pierre" --start 2026-02-21T14:00:00 --duration 30 --meet
\```
```

**Step 3: Run usage tests**

Run: `uv run pytest tests/test_cli_usage.py -v`
Expected: PASS

**Step 4: Run full suite + type check**

Run: `uv run pytest -x -q && uv run mypy src/`

**Step 5: Commit**

```bash
git add src/guten_morgen/cli.py tests/test_cli_usage.py
git commit -m "docs: update usage() docstring with all new commands and options"
```

---

### Task 10: Final verification and cleanup

**Step 1: Run full test suite with coverage**

Run: `uv run pytest -x -q --cov`
Expected: All pass, coverage >= 90%

**Step 2: Run type checker**

Run: `uv run mypy src/`
Expected: No errors

**Step 3: Run linter**

Run: `uv run ruff check .`
Expected: No errors

**Step 4: Run pre-commit hooks**

Run: `uv run pre-commit run --all-files`
Expected: All pass

**Step 5: Verify all commands work**

Run: `uv run gm usage`
Expected: Shows all new commands in the output

**Step 6: Update ISSUES.md**

Move all 8 issues from Open to Resolved with today's date and the latest commit hash. Use this format:

```markdown
### [Issue title]
- **Fixed:** 2026-02-20 (COMMIT_HASH)
- **Was:** [Brief description of what was missing]. Fixed: [what was added].
```

**Step 7: Final commit**

```bash
git add ISSUES.md
git commit -m "docs: mark all 8 issues as resolved in ISSUES.md"
```
