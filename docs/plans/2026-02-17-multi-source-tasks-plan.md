# Multi-Source Tasks & Scheduling — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable the morgen CLI to list tasks from all connected sources (Morgen, Linear, Notion), normalize their metadata, and time-block tasks into the calendar via `tasks schedule`.

**Architecture:** Fan-out across task-integration accounts, normalize external task labels in the output layer (`enrich_tasks()`), add `tasks schedule` as a task-centric time-blocking command. All changes follow existing patterns: `enrich_events()` for output enrichment, `list_all_events()` for multi-account fan-out, `.config.toml` for user config.

**Tech Stack:** Python 3.12+, Click, httpx, pytest with MockTransport/CliRunner

**Design doc:** `docs/plans/2026-02-17-multi-source-tasks-design.md`

**Worktree:** `.worktrees/feat-tasks` (branch: `feat/tasks`)

---

### Task 1: Add multi-source test fixtures

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Add task-integration accounts and external task data to conftest**

Add these fake data structures after the existing `FAKE_TAGS` list (line 169):

```python
# Task-integration accounts (Linear, Notion)
FAKE_TASK_ACCOUNTS = [
    {
        "id": "acc-linear",
        "providerUserDisplayName": "test@company.com",
        "preferredEmail": "test@company.com",
        "integrationId": "linear",
        "integrationGroups": ["tasks"],
    },
    {
        "id": "acc-notion",
        "providerUserDisplayName": "Test User",
        "preferredEmail": "test@example.com",
        "integrationId": "notion",
        "integrationGroups": ["tasks"],
    },
]

FAKE_LINEAR_TASKS = {
    "data": {
        "tasks": [
            {
                "@type": "Task",
                "id": "linear-task-1",
                "title": "Budget planning",
                "progress": "needs-action",
                "priority": 0,
                "due": "2026-02-20",
                "integrationId": "linear",
                "accountId": "acc-linear",
                "links": {
                    "original": {
                        "@type": "Link",
                        "href": "https://linear.app/company/issue/ENG-1740/budget-planning",
                        "title": "Open in Linear",
                    }
                },
                "labels": [
                    {"id": "identifier", "value": "ENG-1740"},
                    {"id": "state", "value": "state-uuid-1"},
                ],
            },
        ],
        "labelDefs": [
            {
                "id": "state",
                "label": "Status",
                "type": "enum",
                "values": [
                    {"value": "state-uuid-1", "label": "In Progress"},
                ],
            },
        ],
        "spaces": [],
    }
}

FAKE_NOTION_TASKS = {
    "data": {
        "tasks": [
            {
                "@type": "Task",
                "id": "notion-task-1",
                "title": "Update Career Ladder",
                "progress": "needs-action",
                "priority": 5,
                "due": "2026-03-01",
                "integrationId": "notion",
                "accountId": "acc-notion",
                "links": {
                    "original": {
                        "@type": "Link",
                        "href": "https://www.notion.so/14ca119c1d9f80ce943a",
                        "title": "Open in Notion",
                    }
                },
                "labels": [
                    {"id": "notion%3A%2F%2Fprojects%2Fstatus_property", "value": "planned"},
                    {"id": "notion%3A%2F%2Fprojects%2Fpriority_property", "value": "priority_high"},
                ],
            },
        ],
        "labelDefs": [
            {
                "id": "notion%3A%2F%2Fprojects%2Fstatus_property",
                "label": "Status",
                "type": "enum",
                "values": [
                    {"value": "planned", "label": "Planning"},
                    {"value": "in-progress", "label": "In Progress"},
                ],
            },
            {
                "id": "notion%3A%2F%2Fprojects%2Fpriority_property",
                "label": "Priority",
                "type": "enum",
                "values": [
                    {"value": "priority_high", "label": "High"},
                    {"value": "priority_medium", "label": "Medium"},
                ],
            },
        ],
        "spaces": [{"id": "space-1", "name": "Projects"}],
    }
}
```

**Step 2: Add task-integration accounts to FAKE_ACCOUNTS and update ROUTES**

Append `FAKE_TASK_ACCOUNTS` entries to `FAKE_ACCOUNTS` (so `list_accounts()` returns them). Update `ROUTES` dict and `mock_transport_handler` to route task list requests by `accountId`:

```python
# Add to FAKE_ACCOUNTS list:
FAKE_ACCOUNTS.extend(FAKE_TASK_ACCOUNTS)  # NOT inline — add after the list definition

# In ROUTES dict, no change needed (default /v3/tasks/list stays as-is for morgen-native)

# In mock_transport_handler, add routing for tasks by accountId (before the existing ROUTES check):
#   if path == "/v3/tasks/list":
#       account_id = dict(request.url.params).get("accountId")
#       if account_id == "acc-linear":
#           return httpx.Response(200, json=FAKE_LINEAR_TASKS)
#       if account_id == "acc-notion":
#           return httpx.Response(200, json=FAKE_NOTION_TASKS)
#       # Default: morgen-native tasks (fall through to ROUTES)
```

**Step 3: Run tests to verify fixtures don't break existing tests**

Run: `cd .worktrees/feat-tasks && uv run pytest -x -v`
Expected: All 152 existing tests pass.

**Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add multi-source task fixtures (linear, notion)"
```

---

### Task 2: Add TTL_TASK_ACCOUNTS and list_task_accounts()

**Files:**
- Modify: `src/morgen/cache.py` (line 16, add constant)
- Modify: `src/morgen/client.py` (after `list_accounts()`, ~line 138)
- Create: `tests/test_client_tasks.py`

**Step 1: Write the failing test**

Create `tests/test_client_tasks.py`:

```python
"""Tests for multi-source task client methods."""
from __future__ import annotations

from morgen.client import MorgenClient


class TestListTaskAccounts:
    def test_returns_only_task_accounts(self, client: MorgenClient) -> None:
        accounts = client.list_task_accounts()
        integration_ids = [a["integrationId"] for a in accounts]
        assert "linear" in integration_ids
        assert "notion" in integration_ids
        # Calendar-only accounts should NOT appear
        assert "google" not in integration_ids
        assert "caldav" not in integration_ids

    def test_cached(self, client: MorgenClient) -> None:
        first = client.list_task_accounts()
        second = client.list_task_accounts()
        assert first == second
```

**Step 2: Run test to verify it fails**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_client_tasks.py -v`
Expected: FAIL — `AttributeError: 'MorgenClient' object has no attribute 'list_task_accounts'`

**Step 3: Add TTL_TASK_ACCOUNTS to cache.py**

In `src/morgen/cache.py`, add after line 16 (`TTL_SINGLE = 300`):

```python
TTL_TASK_ACCOUNTS = 604800  # 7 days
```

**Step 4: Implement list_task_accounts() in client.py**

In `src/morgen/client.py`, add import of `TTL_TASK_ACCOUNTS` to the cache imports (line 16), then add method after `list_accounts()` (~line 138):

```python
def list_task_accounts(self) -> list[dict[str, Any]]:
    """List accounts with task integrations (Linear, Notion, etc.)."""
    cached = self._cache_get("task_accounts")
    if cached is not None:
        return cast(list[dict[str, Any]], cached)
    accounts = self.list_accounts()
    result = [a for a in accounts if "tasks" in a.get("integrationGroups", [])]
    self._cache_set("task_accounts", result, TTL_TASK_ACCOUNTS)
    return result
```

**Step 5: Run test to verify it passes**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_client_tasks.py -v`
Expected: PASS

**Step 6: Run full suite**

Run: `cd .worktrees/feat-tasks && uv run pytest -x -v`
Expected: All tests pass.

**Step 7: Commit**

```bash
git add src/morgen/cache.py src/morgen/client.py tests/test_client_tasks.py
git commit -m "feat: list_task_accounts() with 7-day cache TTL"
```

---

### Task 3: Add enrich_tasks() for output normalization

**Files:**
- Modify: `src/morgen/output.py` (after `enrich_events()`, ~line 154)
- Modify: `tests/test_output.py`

**Step 1: Write the failing tests**

Add to `tests/test_output.py`:

```python
from morgen.output import enrich_tasks


class TestEnrichTasks:
    def test_morgen_native_task(self) -> None:
        tasks = [{"id": "t1", "title": "Review PR", "integrationId": "morgen", "progress": "needs-action"}]
        result = enrich_tasks(tasks)
        assert result[0]["source"] == "morgen"
        assert result[0]["source_id"] is None
        assert result[0]["source_url"] is None
        assert result[0]["source_status"] is None

    def test_linear_task(self) -> None:
        tasks = [{
            "id": "lt1",
            "title": "Budget planning",
            "integrationId": "linear",
            "progress": "needs-action",
            "links": {"original": {"href": "https://linear.app/co/issue/ENG-1740/budget"}},
            "labels": [
                {"id": "identifier", "value": "ENG-1740"},
                {"id": "state", "value": "state-1"},
            ],
        }]
        label_defs = [
            {"id": "state", "label": "Status", "type": "enum",
             "values": [{"value": "state-1", "label": "In Progress"}]},
        ]
        result = enrich_tasks(tasks, label_defs=label_defs)
        assert result[0]["source"] == "linear"
        assert result[0]["source_id"] == "ENG-1740"
        assert result[0]["source_url"] == "https://linear.app/co/issue/ENG-1740/budget"
        assert result[0]["source_status"] == "In Progress"

    def test_notion_task(self) -> None:
        tasks = [{
            "id": "nt1",
            "title": "Update Ladder",
            "integrationId": "notion",
            "progress": "needs-action",
            "links": {"original": {"href": "https://www.notion.so/abc123"}},
            "labels": [
                {"id": "notion%3A%2F%2Fprojects%2Fstatus_property", "value": "in-progress"},
            ],
        }]
        label_defs = [
            {"id": "notion%3A%2F%2Fprojects%2Fstatus_property", "label": "Status", "type": "enum",
             "values": [{"value": "in-progress", "label": "In Progress"}]},
        ]
        result = enrich_tasks(tasks, label_defs=label_defs)
        assert result[0]["source"] == "notion"
        assert result[0]["source_url"] == "https://www.notion.so/abc123"
        assert result[0]["source_status"] == "In Progress"

    def test_no_labels_graceful(self) -> None:
        tasks = [{"id": "t1", "title": "Bare task", "progress": "needs-action"}]
        result = enrich_tasks(tasks)
        assert result[0]["source"] == "morgen"  # default when integrationId missing
        assert result[0]["source_id"] is None
```

**Step 2: Run test to verify it fails**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_output.py::TestEnrichTasks -v`
Expected: FAIL — `ImportError: cannot import name 'enrich_tasks'`

**Step 3: Implement enrich_tasks() in output.py**

Add after `enrich_events()` in `src/morgen/output.py`:

```python
def _resolve_label(labels: list[dict[str, Any]], label_id: str) -> str | None:
    """Find a label value by its id in a task's labels list."""
    for lbl in labels:
        if lbl.get("id") == label_id:
            return lbl.get("value")
    return None


def _resolve_label_display(
    label_value: str | None, label_defs: list[dict[str, Any]], label_id: str
) -> str | None:
    """Map an opaque label value to its human-readable display name via labelDefs."""
    if label_value is None:
        return None
    for defn in label_defs:
        if defn.get("id") != label_id:
            continue
        for val in defn.get("values", []):
            if val.get("value") == label_value:
                return val.get("label")
    return label_value  # Fallback: return raw value if no mapping found


def enrich_tasks(
    tasks: list[dict[str, Any]],
    *,
    label_defs: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Add source, source_id, source_url, source_status to tasks (shallow copy).

    Normalizes external task metadata (Linear labels, Notion properties) into
    common fields so the agent never needs to learn source-specific schemas.
    """
    defs = label_defs or []
    enriched: list[dict[str, Any]] = []
    for task in tasks:
        t = {**task}
        labels = t.get("labels", [])
        integration = t.get("integrationId", "morgen")

        t["source"] = integration

        # source_url: from links.original.href
        links = t.get("links", {})
        original = links.get("original", {})
        t["source_url"] = original.get("href") if original else None

        # source_id: Linear uses labels[id=identifier], others use None
        t["source_id"] = _resolve_label(labels, "identifier")

        # source_status: resolve via label defs
        # Linear uses "state", Notion uses "notion://projects/status_property"
        status_label_ids = ["state", "notion%3A%2F%2Fprojects%2Fstatus_property"]
        t["source_status"] = None
        for sid in status_label_ids:
            raw = _resolve_label(labels, sid)
            if raw is not None:
                t["source_status"] = _resolve_label_display(raw, defs, sid)
                break

        enriched.append(t)
    return enriched
```

**Step 4: Run test to verify it passes**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_output.py::TestEnrichTasks -v`
Expected: PASS

**Step 5: Run full suite + type check**

Run: `cd .worktrees/feat-tasks && uv run pytest -x && uv run mypy src/`
Expected: All pass, no type errors.

**Step 6: Commit**

```bash
git add src/morgen/output.py tests/test_output.py
git commit -m "feat: enrich_tasks() normalizes external task metadata"
```

---

### Task 4: Add list_all_tasks() fan-out in client

**Files:**
- Modify: `src/morgen/client.py` (after `list_task_accounts()`)
- Modify: `tests/test_client_tasks.py`

**Step 1: Write the failing test**

Add to `tests/test_client_tasks.py`:

```python
class TestListAllTasks:
    def test_returns_all_sources(self, client: MorgenClient) -> None:
        result = client.list_all_tasks()
        sources = {t.get("integrationId", "morgen") for t in result["tasks"]}
        assert "morgen" in sources
        assert "linear" in sources
        assert "notion" in sources

    def test_includes_label_defs(self, client: MorgenClient) -> None:
        result = client.list_all_tasks()
        assert "labelDefs" in result
        assert len(result["labelDefs"]) > 0

    def test_source_filter(self, client: MorgenClient) -> None:
        result = client.list_all_tasks(source="linear")
        sources = {t.get("integrationId") for t in result["tasks"]}
        assert sources == {"linear"}

    def test_morgen_only(self, client: MorgenClient) -> None:
        result = client.list_all_tasks(source="morgen")
        sources = {t.get("integrationId", "morgen") for t in result["tasks"]}
        assert sources == {"morgen"}
```

**Step 2: Run test to verify it fails**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_client_tasks.py::TestListAllTasks -v`
Expected: FAIL — `AttributeError: 'MorgenClient' object has no attribute 'list_all_tasks'`

**Step 3: Implement list_all_tasks()**

Add to `src/morgen/client.py` after `list_task_accounts()`:

```python
def list_all_tasks(
    self,
    *,
    source: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List tasks across all connected task sources.

    Returns {"tasks": [...], "labelDefs": [...], "spaces": [...]}
    with tasks merged from all sources.

    If source is specified, only fetch from that integration.
    "morgen" fetches native tasks (no accountId param).
    """
    all_tasks: list[dict[str, Any]] = []
    all_label_defs: list[dict[str, Any]] = []
    all_spaces: list[dict[str, Any]] = []

    # Morgen-native tasks
    if source is None or source == "morgen":
        data = self._request("GET", "/tasks/list", params={"limit": limit})
        morgen_tasks = _extract_list(data, "tasks")
        # Tag morgen-native tasks with integrationId if missing
        for t in morgen_tasks:
            t.setdefault("integrationId", "morgen")
        all_tasks.extend(morgen_tasks)

    # External task sources
    task_accounts = self.list_task_accounts()
    for account in task_accounts:
        integration = account.get("integrationId", "")
        if source is not None and integration != source:
            continue
        account_id = account.get("id", account.get("_id", ""))
        if not account_id:
            continue

        cache_key = f"tasks/{account_id}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            cached_data = cast(dict[str, Any], cached)
        else:
            raw = self._request(
                "GET", "/tasks/list", params={"accountId": account_id, "limit": limit}
            )
            cached_data = raw.get("data", raw) if isinstance(raw, dict) else {}
            self._cache_set(cache_key, cached_data, TTL_TASKS)

        all_tasks.extend(cached_data.get("tasks", []))
        all_label_defs.extend(cached_data.get("labelDefs", []))
        all_spaces.extend(cached_data.get("spaces", []))

    return {"tasks": all_tasks, "labelDefs": all_label_defs, "spaces": all_spaces}
```

**Step 4: Run test to verify it passes**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_client_tasks.py -v`
Expected: PASS

**Step 5: Run full suite + type check**

Run: `cd .worktrees/feat-tasks && uv run pytest -x && uv run mypy src/`
Expected: All pass.

**Step 6: Commit**

```bash
git add src/morgen/client.py tests/test_client_tasks.py
git commit -m "feat: list_all_tasks() fans out across all task sources"
```

---

### Task 5: Add --source and --group-by-source to tasks list CLI

**Files:**
- Modify: `src/morgen/cli.py` (tasks_list function, ~line 575-643)
- Modify: `tests/test_cli_tasks.py`

**Step 1: Write the failing tests**

Add to `tests/test_cli_tasks.py`:

```python
class TestTasksListMultiSource:
    """Multi-source task listing."""

    def test_all_sources_by_default(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        sources = {t.get("source", "morgen") for t in data}
        assert "morgen" in sources
        assert "linear" in sources
        assert "notion" in sources

    def test_source_filter(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "list", "--json", "--source", "linear"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        sources = {t["source"] for t in data}
        assert sources == {"linear"}

    def test_source_morgen_only(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "list", "--json", "--source", "morgen"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        sources = {t["source"] for t in data}
        assert sources == {"morgen"}

    def test_enriched_fields(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "list", "--json", "--source", "linear"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        task = data[0]
        assert task["source"] == "linear"
        assert task["source_id"] == "ENG-1740"
        assert "linear.app" in task["source_url"]
        assert task["source_status"] == "In Progress"

    def test_group_by_source(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "list", "--json", "--group-by-source"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "morgen" in data
        assert "linear" in data
        assert "notion" in data
        assert isinstance(data["morgen"], list)
```

**Step 2: Run test to verify they fail**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_cli_tasks.py::TestTasksListMultiSource -v`
Expected: FAIL

**Step 3: Update tasks_list in cli.py**

Update `TASK_COLUMNS` and `TASK_CONCISE_FIELDS` (line 566-567):

```python
TASK_COLUMNS = ["id", "title", "source", "source_id", "progress", "priority", "due", "taskListId"]
TASK_CONCISE_FIELDS = ["id", "title", "source", "source_id", "progress", "due"]
```

Add `--source` and `--group-by-source` flags, and rewrite the tasks_list function to use `list_all_tasks()` + `enrich_tasks()`:

```python
@tasks.command("list")
@click.option("--limit", default=100, type=int, help="Max tasks per source.")
@click.option("--source", "source_filter", default=None, help="Filter by source (morgen, linear, notion).")
@click.option("--group-by-source", is_flag=True, default=False, help="Group output by source.")
@click.option(
    "--status", "status_filter",
    type=click.Choice(["open", "completed", "all"]), default="all",
    help="Filter by status.",
)
@click.option("--due-before", default=None, help="Tasks due before (ISO 8601).")
@click.option("--due-after", default=None, help="Tasks due after (ISO 8601).")
@click.option("--overdue", is_flag=True, default=False, help="Show only overdue tasks.")
@click.option("--priority", "priority_filter", default=None, type=int, help="Filter by priority.")
@output_options
def tasks_list(
    limit: int,
    source_filter: str | None,
    group_by_source: bool,
    status_filter: str,
    due_before: str | None,
    due_after: str | None,
    overdue: bool,
    priority_filter: int | None,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
) -> None:
    """List tasks from all connected sources."""
    try:
        client = _get_client()
        result = client.list_all_tasks(source=source_filter, limit=limit)

        from morgen.output import enrich_tasks
        data = enrich_tasks(result["tasks"], label_defs=result.get("labelDefs", []))

        # Apply client-side filters (same logic as before)
        if overdue:
            from datetime import datetime, timezone
            due_before = datetime.now(timezone.utc).isoformat()

        filtered: list[dict[str, Any]] = []
        for t in data:
            progress = t.get("progress", "")
            if status_filter == "open" and progress == "completed":
                continue
            if status_filter == "completed" and progress != "completed":
                continue
            due = t.get("due", "")
            if due_before and due:
                if due[:10] >= due_before[:10]:
                    continue
            if due_after and due:
                if due[:10] <= due_after[:10]:
                    continue
            if (due_before or due_after) and not due:
                continue
            if priority_filter is not None and t.get("priority") != priority_filter:
                continue
            filtered.append(t)

        if group_by_source:
            grouped: dict[str, list[dict[str, Any]]] = {}
            for t in filtered:
                src = t.get("source", "morgen")
                grouped.setdefault(src, []).append(t)
            if response_format == "concise" and not fields:
                from morgen.output import select_fields
                grouped = {k: select_fields(v, TASK_CONCISE_FIELDS) for k, v in grouped.items()}
            morgen_output(grouped, fmt="json" if fmt in ("json", "jsonl") else fmt)
        else:
            if response_format == "concise" and not fields:
                fields = TASK_CONCISE_FIELDS
            morgen_output(filtered, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=TASK_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)
```

**Step 4: Run tests to verify they pass**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_cli_tasks.py -v`
Expected: All task CLI tests pass (old + new).

**Step 5: Run full suite + type check + lint**

Run: `cd .worktrees/feat-tasks && uv run pytest -x && uv run mypy src/ && uv run ruff check .`
Expected: All pass.

**Step 6: Commit**

```bash
git add src/morgen/cli.py tests/test_cli_tasks.py
git commit -m "feat: multi-source tasks list with --source and --group-by-source"
```

---

### Task 6: Update combined views to use list_all_tasks()

**Files:**
- Modify: `src/morgen/cli.py` (`_combined_view()`, ~line 955-1046)
- Modify: `tests/test_cli_views.py`

**Step 1: Write the failing test**

Add to `tests/test_cli_views.py`:

```python
class TestViewsMultiSource:
    """Combined views include tasks from all sources."""

    def test_today_includes_external_tasks(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["today", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Collect all task titles across all task categories
        all_tasks = data.get("scheduled_tasks", []) + data.get("overdue_tasks", []) + data.get("unscheduled_tasks", [])
        sources = {t.get("source", "morgen") for t in all_tasks}
        # Should include external sources
        assert "linear" in sources or "notion" in sources
```

**Step 2: Run test to verify it fails**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_cli_views.py::TestViewsMultiSource -v`
Expected: FAIL — tasks won't have `source` field yet in combined views.

**Step 3: Update _combined_view() to use list_all_tasks() + enrich_tasks()**

In `_combined_view()`, replace the tasks section (~line 991-1017) — change `client.list_tasks()` to `client.list_all_tasks()` and add enrichment:

```python
        if not events_only:
            result = client.list_all_tasks()
            from morgen.output import enrich_tasks
            tasks_data = enrich_tasks(result["tasks"], label_defs=result.get("labelDefs", []))

            scheduled: list[dict[str, Any]] = []
            overdue: list[dict[str, Any]] = []
            unscheduled: list[dict[str, Any]] = []
            start_date = start[:10]
            end_date = end[:10]
            for t in tasks_data:
                due = t.get("due", "")
                if due:
                    due_date = due[:10]
                    if start_date <= due_date <= end_date:
                        scheduled.append(t)
                    elif due_date < start_date:
                        overdue.append(t)
                else:
                    unscheduled.append(t)
            # ... rest unchanged
```

**Step 4: Run tests**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_cli_views.py -v`
Expected: All view tests pass.

**Step 5: Full suite**

Run: `cd .worktrees/feat-tasks && uv run pytest -x && uv run mypy src/`
Expected: All pass.

**Step 6: Commit**

```bash
git add src/morgen/cli.py tests/test_cli_views.py
git commit -m "feat: combined views include tasks from all connected sources"
```

---

### Task 7: Add --duration to tasks create/update

**Files:**
- Modify: `src/morgen/cli.py` (tasks_create and tasks_update commands)
- Modify: `tests/test_cli_tasks.py`

**Step 1: Write failing test**

Add to `tests/test_cli_tasks.py`:

```python
class TestTasksDuration:
    def test_create_with_duration(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["tasks", "create", "--title", "Quick task", "--duration", "30"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("estimatedDuration") == "PT30M"

    def test_update_with_duration(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["tasks", "update", "task-1", "--duration", "45"]
        )
        assert result.exit_code == 0
```

**Step 2: Run test to verify it fails**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_cli_tasks.py::TestTasksDuration -v`
Expected: FAIL — `No such option: --duration`

**Step 3: Add --duration to tasks_create and tasks_update**

In `tasks_create` (~line 667), add option:
```python
@click.option("--duration", default=None, type=int, help="Estimated duration in minutes.")
```

In the function body, add:
```python
if duration is not None:
    task_data["estimatedDuration"] = f"PT{duration}M"
```

Same for `tasks_update` (~line 694).

**Step 4: Run test to verify it passes**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_cli_tasks.py::TestTasksDuration -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/morgen/cli.py tests/test_cli_tasks.py
git commit -m "feat: --duration flag on tasks create/update for AI planner metadata"
```

---

### Task 8: Add task_calendar config to groups.py

**Files:**
- Modify: `src/morgen/groups.py` (MorgenConfig dataclass, load_morgen_config)
- Modify: `tests/test_config.py` (or create test for task_calendar)

**Step 1: Write failing test**

Add test (in existing config test file or new):

```python
def test_load_task_calendar(tmp_path):
    config_file = tmp_path / ".config.toml"
    config_file.write_text('task_calendar = "cal-tasks"\ntask_calendar_account = "acc-1"\n')
    from morgen.groups import load_morgen_config
    config = load_morgen_config(path=config_file)
    assert config.task_calendar == "cal-tasks"
    assert config.task_calendar_account == "acc-1"

def test_load_task_calendar_defaults(tmp_path):
    config_file = tmp_path / ".config.toml"
    config_file.write_text("")
    from morgen.groups import load_morgen_config
    config = load_morgen_config(path=config_file)
    assert config.task_calendar is None
    assert config.task_calendar_account is None
```

**Step 2: Run test to verify it fails**

Expected: FAIL — `MorgenConfig` has no attribute `task_calendar`.

**Step 3: Add fields to MorgenConfig and load_morgen_config**

In `src/morgen/groups.py`, add to `MorgenConfig` dataclass (~line 31):

```python
@dataclass
class MorgenConfig:
    """Top-level morgen configuration."""

    default_group: str | None = None
    active_only: bool = False
    groups: dict[str, GroupConfig] = field(default_factory=dict)
    task_calendar: str | None = None
    task_calendar_account: str | None = None
```

In `load_morgen_config()`, add before the return (~line 74):

```python
return MorgenConfig(
    default_group=raw.get("default_group"),
    active_only=raw.get("active_only", False),
    groups=groups,
    task_calendar=raw.get("task_calendar"),
    task_calendar_account=raw.get("task_calendar_account"),
)
```

**Step 4: Run tests**

Run: `cd .worktrees/feat-tasks && uv run pytest -x && uv run mypy src/`
Expected: All pass.

**Step 5: Commit**

```bash
git add src/morgen/groups.py tests/
git commit -m "feat: task_calendar config fields in MorgenConfig"
```

---

### Task 9: Add schedule_task() to client

**Files:**
- Modify: `src/morgen/client.py` (after `list_all_tasks()`)
- Modify: `tests/test_client_tasks.py`

**Step 1: Write failing test**

Add to `tests/test_client_tasks.py`:

```python
class TestScheduleTask:
    def test_creates_linked_event(self, client: MorgenClient) -> None:
        result = client.schedule_task(
            task_id="task-1",
            start="2026-02-18T09:00:00",
            calendar_id="cal-1",
            account_id="acc-1",
        )
        assert result["morgen.so:metadata"]["taskId"] == "task-1"
        assert result["start"] == "2026-02-18T09:00:00"

    def test_derives_duration_from_task(self, client: MorgenClient) -> None:
        # Mock a task with estimatedDuration — the mock returns a generic task,
        # so we test the fallback default duration
        result = client.schedule_task(
            task_id="task-1",
            start="2026-02-18T09:00:00",
            calendar_id="cal-1",
            account_id="acc-1",
        )
        # Default duration when task has no estimatedDuration
        assert result["duration"] == "PT30M"

    def test_explicit_duration(self, client: MorgenClient) -> None:
        result = client.schedule_task(
            task_id="task-1",
            start="2026-02-18T09:00:00",
            duration="PT45M",
            calendar_id="cal-1",
            account_id="acc-1",
        )
        assert result["duration"] == "PT45M"
```

**Step 2: Run test to verify it fails**

Expected: FAIL — `AttributeError: 'MorgenClient' object has no attribute 'schedule_task'`

**Step 3: Implement schedule_task()**

Add to `src/morgen/client.py`:

```python
def schedule_task(
    self,
    task_id: str,
    start: str,
    duration: str | None = None,
    calendar_id: str | None = None,
    account_id: str | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    """Create a calendar event linked to a task (time-blocking).

    Auto-derives title and duration from the task if not specified.
    """
    task = self.get_task(task_id)

    # Derive title
    title = task.get("title", "Task")

    # Derive duration: explicit > task estimatedDuration > 30min default
    if duration is None:
        duration = task.get("estimatedDuration", "PT30M")

    # Derive timezone
    if timezone is None:
        timezone = task.get("timeZone")

    event_data: dict[str, Any] = {
        "title": title,
        "start": start,
        "duration": duration,
        "calendarId": calendar_id or "",
        "accountId": account_id or "",
        "showWithoutTime": False,
        "morgen.so:metadata": {"taskId": task_id},
    }
    if timezone:
        event_data["timeZone"] = timezone

    data = self._request("POST", "/events/create", json=event_data)
    self._cache_invalidate("events")
    return _extract_single(data, "event")
```

**Step 4: Run test to verify it passes**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_client_tasks.py::TestScheduleTask -v`
Expected: PASS

**Step 5: Full suite + types**

Run: `cd .worktrees/feat-tasks && uv run pytest -x && uv run mypy src/`
Expected: All pass.

**Step 6: Commit**

```bash
git add src/morgen/client.py tests/test_client_tasks.py
git commit -m "feat: schedule_task() creates calendar event linked to task"
```

---

### Task 10: Add tasks schedule CLI command

**Files:**
- Modify: `src/morgen/cli.py` (after tasks_delete, ~line 774)
- Modify: `tests/test_cli_tasks.py`

**Step 1: Write failing test**

Add to `tests/test_cli_tasks.py`:

```python
class TestTasksSchedule:
    def test_schedule(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["tasks", "schedule", "task-1", "--start", "2026-02-18T09:00:00"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "scheduled"
        assert "eventId" in data
        assert "taskId" in data

    def test_schedule_with_duration(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["tasks", "schedule", "task-1", "--start", "2026-02-18T09:00:00", "--duration", "60"]
        )
        assert result.exit_code == 0

    def test_schedule_missing_start(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "schedule", "task-1"])
        assert result.exit_code != 0
```

**Step 2: Run test to verify it fails**

Expected: FAIL — `No such command 'schedule'`

**Step 3: Implement tasks schedule command**

Add to `src/morgen/cli.py` after `tasks_delete`:

```python
@tasks.command("schedule")
@click.argument("task_id")
@click.option("--start", required=True, help="Start datetime (ISO 8601).")
@click.option("--duration", default=None, type=int, help="Duration in minutes (default: from task or 30).")
@click.option("--calendar-id", default=None, help="Calendar ID (from .config.toml if omitted).")
@click.option("--account-id", default=None, help="Account ID (auto-discovered if omitted).")
def tasks_schedule(
    task_id: str,
    start: str,
    duration: int | None,
    calendar_id: str | None,
    account_id: str | None,
) -> None:
    """Time-block a task into the calendar."""
    try:
        client = _get_client()

        # Resolve calendar from config if not specified
        if not calendar_id or not account_id:
            config = load_morgen_config()
            if config.task_calendar and not calendar_id:
                calendar_id = config.task_calendar
            if config.task_calendar_account and not account_id:
                account_id = config.task_calendar_account
        if not calendar_id or not account_id:
            account_id, cal_ids = _auto_discover(client)
            calendar_id = calendar_id or cal_ids[0]

        dur_str = f"PT{duration}M" if duration else None

        from morgen.time_utils import get_local_timezone
        result = client.schedule_task(
            task_id=task_id,
            start=start,
            duration=dur_str,
            calendar_id=calendar_id,
            account_id=account_id,
            timezone=get_local_timezone(),
        )
        output = {
            "status": "scheduled",
            "taskId": task_id,
            "eventId": result.get("id", ""),
            "start": result.get("start", start),
            "duration": result.get("duration", dur_str or "PT30M"),
        }
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)
```

**Step 4: Run tests**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_cli_tasks.py::TestTasksSchedule -v`
Expected: PASS

**Step 5: Full suite + types + lint**

Run: `cd .worktrees/feat-tasks && uv run pytest -x && uv run mypy src/ && uv run ruff check .`
Expected: All pass.

**Step 6: Commit**

```bash
git add src/morgen/cli.py tests/test_cli_tasks.py
git commit -m "feat: tasks schedule command for time-blocking"
```

---

### Task 11: Update usage command with dynamic sources and scenarios

**Files:**
- Modify: `src/morgen/cli.py` (`usage()` function, ~line 144-282)
- Modify: `tests/test_cli_usage.py`

**Step 1: Write failing test**

Add to `tests/test_cli_usage.py`:

```python
def test_usage_shows_task_sources(runner, mock_client):
    result = runner.invoke(cli, ["usage"])
    assert result.exit_code == 0
    assert "Connected Task Sources" in result.output
    assert "linear" in result.output
    assert "notion" in result.output

def test_usage_shows_schedule_command(runner, mock_client):
    result = runner.invoke(cli, ["usage"])
    assert "tasks schedule" in result.output

def test_usage_shows_scenarios(runner, mock_client):
    result = runner.invoke(cli, ["usage"])
    assert "Morning Triage" in result.output
    assert "Schedule a Linear Issue" in result.output
```

**Step 2: Run test to verify it fails**

Expected: FAIL — current usage doesn't contain these strings.

**Step 3: Update usage() function**

Add dynamic source discovery and update the text template in `usage()`. Add a helper to query task accounts and format them:

At the top of `usage()`, after loading config:
```python
# Dynamic task source discovery
try:
    client = _get_client()
    task_accounts = client.list_task_accounts()
    source_lines = ["  - morgen (native tasks)"]
    for acc in task_accounts:
        name = acc.get("providerUserDisplayName", "")
        iid = acc.get("integrationId", "")
        source_lines.append(f"  - {iid} ({name})")
    sources_section = "\n".join(source_lines)
except Exception:
    sources_section = "  (run `morgen accounts` to check connections)"
```

Then update the text template to include sources, the `tasks schedule` command, `--source`/`--duration` flags, updated workflow, and scenario docs.

**Step 4: Run tests**

Run: `cd .worktrees/feat-tasks && uv run pytest tests/test_cli_usage.py -v`
Expected: PASS

**Step 5: Full suite**

Run: `cd .worktrees/feat-tasks && uv run pytest -x && uv run mypy src/ && uv run ruff check .`
Expected: All pass.

**Step 6: Commit**

```bash
git add src/morgen/cli.py tests/test_cli_usage.py
git commit -m "feat: usage shows dynamic task sources and scenario docs"
```

---

### Task 12: Final integration test and cleanup

**Step 1: Run full suite one last time**

Run: `cd .worktrees/feat-tasks && uv run pytest -x -v && uv run mypy src/ && uv run ruff check .`
Expected: All pass, no warnings.

**Step 2: Verify the complete workflow manually**

Run: `cd .worktrees/feat-tasks && uv run morgen usage | head -80`
Verify: Sources listed, schedule command documented, scenarios shown.

**Step 3: Commit any stragglers, then done**

```bash
git log --oneline feat/tasks ^master
```

Verify: Clean commit history, one commit per feature.
