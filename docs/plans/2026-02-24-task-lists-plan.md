# Task Lists Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add full task list CRUD support (`gm lists`) and `--list` option on task commands.

**Architecture:** v2 API methods on MorgenClient (full URL pattern like RSVP), new `TaskList` model, `gm lists` CLI group mirroring `gm tags`, `--list` option on `tasks create/update/list` with name-based resolution.

**Tech Stack:** Python 3.10+, Pydantic v2, Click, httpx, pytest

---

### Task 1: TaskList Model

**Files:**
- Modify: `src/guten_morgen/models.py`
- Test: `tests/test_models.py`

**Step 1: Write the failing test**

In `tests/test_models.py`, add:

```python
class TestTaskList:
    def test_from_api_response(self) -> None:
        data = {
            "@type": "TaskList",
            "serviceName": "morgen",
            "id": "07134c5c-1183-4f8c-9716-4c58257694c8@morgen.so",
            "name": "Run - Work",
            "color": "#38c2c7",
            "role": None,
            "position": 1761671965352,
            "created": "2025-10-28T17:19:25Z",
            "updated": "2025-10-28T17:19:32.616Z",
            "myRights": {"mayAdmin": True, "mayDelete": True},
            "accountId": None,
        }
        tl = TaskList.model_validate(data)
        assert tl.id == "07134c5c-1183-4f8c-9716-4c58257694c8@morgen.so"
        assert tl.name == "Run - Work"
        assert tl.color == "#38c2c7"
        assert tl.position == 1761671965352

    def test_inbox_role(self) -> None:
        data = {"id": "inbox", "name": "Inbox", "role": "inbox", "color": "#9695A0"}
        tl = TaskList.model_validate(data)
        assert tl.role == "inbox"

    def test_extra_fields_ignored(self) -> None:
        data = {"id": "test", "name": "Test", "myRights": {"mayAdmin": True}, "accountId": None}
        tl = TaskList.model_validate(data)
        assert tl.id == "test"
```

Add import at top: `from guten_morgen.models import TaskList` (alongside existing imports).

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py::TestTaskList -v`
Expected: FAIL with `ImportError: cannot import name 'TaskList'`

**Step 3: Write minimal implementation**

In `src/guten_morgen/models.py`, add after the `Tag` class:

```python
class TaskList(MorgenModel):
    """Task list (project/folder for tasks)."""

    id: str
    name: str
    color: str | None = None
    role: str | None = None
    serviceName: str | None = None
    position: int | None = None
    created: str | None = None
    updated: str | None = None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py::TestTaskList -v`
Expected: PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/models.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/guten_morgen/models.py tests/test_models.py
git commit -m "feat(models): add TaskList model for v2 task lists API"
```

---

### Task 2: Client — list_task_lists

**Files:**
- Modify: `src/guten_morgen/client.py`
- Modify: `src/guten_morgen/cache.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_client.py`

**Step 1: Add fake data and route to conftest.py**

In `tests/conftest.py`, add fake task lists data after `FAKE_TAGS`:

```python
FAKE_TASK_LISTS = [
    {"id": "inbox", "name": "Inbox", "color": "#9695A0", "role": "inbox", "serviceName": "morgen"},
    {
        "id": "list-work@morgen.so",
        "name": "Run - Work",
        "color": "#38c2c7",
        "serviceName": "morgen",
        "position": 1761671965352,
        "created": "2025-10-28T17:19:25Z",
        "updated": "2025-10-28T17:19:32.616Z",
    },
    {
        "id": "list-family@morgen.so",
        "name": "Run - Family",
        "color": "#ff8f1e",
        "serviceName": "morgen",
        "position": 1761630397298,
    },
]
```

Add a v2 route in `mock_transport_handler`, before the `if path in ROUTES:` check:

```python
    # v2 task lists API
    if path == "/v2/taskLists/list":
        return httpx.Response(200, json=FAKE_TASK_LISTS)
```

Also add v2 POST handling for create/update/delete before the existing `if request.method == "POST":` block:

```python
    # v2 task lists POST endpoints
    if request.method == "POST" and path.startswith("/v2/taskLists/"):
        try:
            body = json.loads(request.content)
        except (json.JSONDecodeError, ValueError):
            body = {}
        body.setdefault("id", "new-list-id@morgen.so")
        if "/delete" in path:
            return httpx.Response(200, json=body)
        return httpx.Response(200, json=body)
```

**Step 2: Write the failing test**

In `tests/test_client.py`, add:

```python
class TestListTaskLists:
    def test_returns_all_lists(self, client: MorgenClient) -> None:
        lists = client.list_task_lists()
        assert len(lists) == 3
        names = [tl.name for tl in lists]
        assert "Inbox" in names
        assert "Run - Work" in names

    def test_inbox_has_role(self, client: MorgenClient) -> None:
        lists = client.list_task_lists()
        inbox = [tl for tl in lists if tl.id == "inbox"][0]
        assert inbox.role == "inbox"
```

Add import for `TaskList` if not already imported in the test file.

**Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_client.py::TestListTaskLists -v`
Expected: FAIL with `AttributeError: 'MorgenClient' object has no attribute 'list_task_lists'`

**Step 4: Write minimal implementation**

In `src/guten_morgen/cache.py`, add:

```python
TTL_TASK_LISTS = 86400  # 24 hours (lists change rarely)
```

In `src/guten_morgen/client.py`:

1. Add import: update the import line to include `TaskList`:
   ```python
   from guten_morgen.models import Account, Calendar, Event, LabelDef, MorgenModel, Space, Tag, Task, TaskList, TaskListResponse
   ```

2. Add import for cache TTL:
   ```python
   from guten_morgen.cache import (
       TTL_ACCOUNTS,
       TTL_CALENDARS,
       TTL_EVENTS,
       TTL_SINGLE,
       TTL_TAGS,
       TTL_TASK_ACCOUNTS,
       TTL_TASK_LISTS,
       TTL_TASKS,
   )
   ```

3. Add constant after `SYNC_BASE_URL`:
   ```python
   V2_BASE_URL = "https://api.morgen.so/v2"
   ```

4. Add method in the `# ----- Tasks -----` section (or create a new `# ----- Task Lists -----` section before Tags):
   ```python
   # ----- Task Lists -----

   def list_task_lists(self) -> list[TaskList]:
       """List all task lists (v2 API)."""
       cached = self._cache_get("taskLists")
       if cached is not None:
           return [TaskList.model_validate(tl) for tl in cast("list[dict[str, Any]]", cached)]
       url = f"{V2_BASE_URL}/taskLists/list"
       data = self._request("GET", url, params={"limit": 100})
       if isinstance(data, list):
           result = [TaskList.model_validate(item) for item in data]
       else:
           result = _extract_list(data, "taskLists", TaskList)
       self._cache_set("taskLists", [tl.model_dump() for tl in result], TTL_TASK_LISTS)
       return result
   ```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_client.py::TestListTaskLists -v`
Expected: PASS

**Step 6: Run mypy**

Run: `uv run mypy src/guten_morgen/client.py src/guten_morgen/cache.py`
Expected: clean

**Step 7: Commit**

```bash
git add src/guten_morgen/client.py src/guten_morgen/cache.py src/guten_morgen/models.py tests/conftest.py tests/test_client.py
git commit -m "feat(client): add list_task_lists via v2 API"
```

---

### Task 3: Client — create, update, delete task lists

**Files:**
- Modify: `src/guten_morgen/client.py`
- Test: `tests/test_client.py`

**Step 1: Write the failing tests**

In `tests/test_client.py`, add:

```python
class TestTaskListCRUD:
    def test_create_task_list(self, client: MorgenClient) -> None:
        result = client.create_task_list({"name": "Project: X", "color": "#ff0000"})
        assert result is not None
        assert result.name == "Project: X"

    def test_update_task_list(self, client: MorgenClient) -> None:
        result = client.update_task_list({"id": "list-work@morgen.so", "name": "Work Tasks"})
        assert result is not None
        assert result.id == "list-work@morgen.so"

    def test_delete_task_list(self, client: MorgenClient) -> None:
        # Should not raise
        client.delete_task_list("list-work@morgen.so")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_client.py::TestTaskListCRUD -v`
Expected: FAIL with `AttributeError`

**Step 3: Write minimal implementation**

In `src/guten_morgen/client.py`, add to the `# ----- Task Lists -----` section:

```python
    def create_task_list(self, data: dict[str, Any]) -> TaskList | None:
        """Create a task list (v2 API)."""
        url = f"{V2_BASE_URL}/taskLists/create"
        result = self._request("POST", url, json=data)
        self._cache_invalidate("taskLists")
        if isinstance(result, dict):
            return TaskList.model_validate(result)
        return None

    def update_task_list(self, data: dict[str, Any]) -> TaskList | None:
        """Update a task list (v2 API)."""
        url = f"{V2_BASE_URL}/taskLists/update"
        result = self._request("POST", url, json=data)
        self._cache_invalidate("taskLists")
        if isinstance(result, dict):
            return TaskList.model_validate(result)
        return None

    def delete_task_list(self, list_id: str) -> None:
        """Delete a task list (v2 API)."""
        url = f"{V2_BASE_URL}/taskLists/delete"
        self._request("POST", url, json={"id": list_id})
        self._cache_invalidate("taskLists")
```

Note: The v2 API returns task list objects directly (not wrapped in `{"data": {"taskList": ...}}`), so we validate directly instead of using `_extract_single`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_client.py::TestTaskListCRUD -v`
Expected: PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/client.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/guten_morgen/client.py tests/test_client.py
git commit -m "feat(client): add task list create/update/delete via v2 API"
```

---

### Task 4: CLI — `gm lists` group (list, create, update, delete)

**Files:**
- Modify: `src/guten_morgen/cli.py`
- Create: `tests/test_cli_lists.py`

**Step 1: Write the failing tests**

Create `tests/test_cli_lists.py`:

```python
"""Tests for lists commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient


class TestListsList:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3
        assert data[0]["name"] == "Inbox"

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "list"])
        assert result.exit_code == 0
        assert "Run - Work" in result.output

    def test_concise(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "list", "--json", "--response-format", "concise"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "id" in data[0]
        assert "name" in data[0]


class TestListsCreate:
    def test_create(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "create", "--name", "Project: X"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "Project: X"

    def test_create_with_color(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "create", "--name", "Test", "--color", "#ff0000"])
        assert result.exit_code == 0


class TestListsUpdate:
    def test_update(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "update", "list-work@morgen.so", "--name", "Work Tasks"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "list-work@morgen.so"
        assert data["name"] == "Work Tasks"


class TestListsDelete:
    def test_delete(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "delete", "list-work@morgen.so"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "deleted"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_lists.py -v`
Expected: FAIL with `Usage: gm [OPTIONS] COMMAND` (no "lists" command)

**Step 3: Write minimal implementation**

In `src/guten_morgen/cli.py`, add a new section after the tags section (before providers):

```python
# ---------------------------------------------------------------------------
# lists (task lists)
# ---------------------------------------------------------------------------

LIST_COLUMNS = ["id", "name", "color", "role"]
LIST_CONCISE_FIELDS = ["id", "name", "color"]


@cli.group()
def lists() -> None:
    """Manage task lists."""


@lists.command("list")
@output_options
def lists_list(fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str) -> None:
    """List all task lists."""
    try:
        client = _get_client(fmt)
        data = [tl.model_dump() for tl in client.list_task_lists()]
        if response_format == "concise" and not fields:
            fields = LIST_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=LIST_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@lists.command("create")
@click.option("--name", required=True, help="List name.")
@click.option("--color", default=None, help="List color (hex).")
def lists_create(name: str, color: str | None) -> None:
    """Create a task list."""
    try:
        client = _get_client()
        list_data: dict[str, Any] = {"name": name}
        if color:
            list_data["color"] = color
        result = client.create_task_list(list_data)
        output = result.model_dump(exclude_none=True) if result else {"status": "created"}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@lists.command("update")
@click.argument("list_id")
@click.option("--name", default=None, help="New list name.")
@click.option("--color", default=None, help="New list color (hex).")
def lists_update(list_id: str, name: str | None, color: str | None) -> None:
    """Update a task list."""
    try:
        client = _get_client()
        list_data: dict[str, Any] = {"id": list_id}
        if name is not None:
            list_data["name"] = name
        if color is not None:
            list_data["color"] = color
        result = client.update_task_list(list_data)
        output = result.model_dump(exclude_none=True) if result else {"status": "updated", "id": list_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@lists.command("delete")
@click.argument("list_id")
def lists_delete(list_id: str) -> None:
    """Delete a task list."""
    try:
        client = _get_client()
        client.delete_task_list(list_id)
        click.echo(json.dumps({"status": "deleted", "id": list_id}))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_lists.py -v`
Expected: PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/cli.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/guten_morgen/cli.py tests/test_cli_lists.py
git commit -m "feat(cli): add gm lists group (list, create, update, delete)"
```

---

### Task 5: `--list` on tasks create and update

**Files:**
- Modify: `src/guten_morgen/cli.py`
- Modify: `tests/test_cli_tasks.py`

**Step 1: Write the failing tests**

In `tests/test_cli_tasks.py`, add (find the existing task create/update test classes and add to them, or create new ones):

```python
class TestTasksCreateWithList:
    def test_create_with_list_name(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "create", "--title", "New task", "--list", "Run - Work"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["taskListId"] == "list-work@morgen.so"

    def test_create_with_list_case_insensitive(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "create", "--title", "New task", "--list", "run - work"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["taskListId"] == "list-work@morgen.so"

    def test_create_with_unknown_list(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "create", "--title", "New task", "--list", "Nonexistent"])
        assert result.exit_code != 0 or "not found" in result.output.lower() or "error" in result.output.lower()


class TestTasksUpdateWithList:
    def test_update_with_list(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "update", "task-1", "--list", "Run - Family"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["taskListId"] == "list-family@morgen.so"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_tasks.py::TestTasksCreateWithList -v`
Expected: FAIL with `no such option: --list`

**Step 3: Write minimal implementation**

In `src/guten_morgen/cli.py`, add a helper function near `_resolve_tag_names`:

```python
def _resolve_list_name(client: MorgenClient, name: str) -> str:
    """Resolve a task list name to its ID. Case-insensitive matching."""
    all_lists = client.list_task_lists()
    name_to_id = {tl.name.lower(): tl.id for tl in all_lists}
    lid = name_to_id.get(name.lower())
    if lid is None:
        available = ", ".join(tl.name for tl in all_lists)
        msg = f"Task list '{name}' not found. Available: {available}"
        raise click.ClickException(msg)
    return lid
```

Add `--list` option to `tasks_create`:

```python
@click.option("--list", "list_name", default=None, help="Task list name. Resolved to ID.")
```

Add to the function signature: `list_name: str | None,`

Add in the body (after the tag_names block):

```python
        if list_name:
            task_data["taskListId"] = _resolve_list_name(client, list_name)
```

Same changes for `tasks_update` — add the `--list` option, the parameter, and the body logic.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_tasks.py::TestTasksCreateWithList tests/test_cli_tasks.py::TestTasksUpdateWithList -v`
Expected: PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/cli.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/guten_morgen/cli.py tests/test_cli_tasks.py
git commit -m "feat(cli): add --list option to tasks create and update"
```

---

### Task 6: `--list` filter on tasks list + list_name enrichment

**Files:**
- Modify: `src/guten_morgen/cli.py`
- Modify: `src/guten_morgen/output.py`
- Modify: `tests/test_cli_tasks.py`

**Step 1: Write the failing tests**

In `tests/test_cli_tasks.py`, add:

```python
class TestTasksListByList:
    def test_filter_by_list_name(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Tasks can be filtered by --list name."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--list", "Inbox"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # All fake tasks have taskListId="inbox"
        assert len(data) > 0
        for t in data:
            assert t.get("list_name") == "Inbox"

    def test_filter_excludes_other_lists(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--list filter excludes tasks in other lists."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--list", "Run - Work"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # No fake tasks are in "Run - Work"
        assert len(data) == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_tasks.py::TestTasksListByList -v`
Expected: FAIL with `no such option: --list`

**Step 3: Write minimal implementation**

In `src/guten_morgen/output.py`, update the `enrich_tasks` function signature and body to accept task lists:

```python
def enrich_tasks(
    tasks: list[dict[str, Any]],
    *,
    label_defs: list[dict[str, Any]] | None = None,
    tags: list[dict[str, Any]] | None = None,
    task_lists: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
```

Add inside, after the `tag_id_to_name` line:

```python
    list_id_to_name: dict[str, str] = {
        tl["id"]: tl["name"] for tl in (task_lists or []) if "id" in tl and "name" in tl
    }
```

Add inside the per-task loop, after the `tag_names` line:

```python
        # list_name: resolve taskListId to human-readable name
        t["list_name"] = list_id_to_name.get(t.get("taskListId", ""))
```

In `src/guten_morgen/cli.py`:

1. Add `"list_name"` to `TASK_COLUMNS` and `TASK_CONCISE_FIELDS`:
   ```python
   TASK_COLUMNS = ["id", "title", "progress", "priority", "due", "list_name", "tag_names", "source", "source_id", "source_status"]
   TASK_CONCISE_FIELDS = ["id", "title", "progress", "due", "list_name", "tag_names", "source"]
   ```

2. Add `--list` option to `tasks_list`:
   ```python
   @click.option("--list", "list_name", default=None, help="Filter by task list name.")
   ```
   And add `list_name: str | None,` to the function signature.

3. In the `tasks_list` body, fetch task lists and pass to enrichment. After the `all_tags = ...` line:
   ```python
           all_task_lists = [tl.model_dump() for tl in client.list_task_lists()]
   ```

4. Update the `enrich_tasks` call to pass task lists:
   ```python
           data = enrich_tasks(data, label_defs=label_defs, tags=all_tags, task_lists=all_task_lists)
   ```

5. Add list filter in the client-side filter loop, after the tag filter block:
   ```python
               # List filter
               if list_name:
                   list_id = _resolve_list_name(client, list_name)
                   if t.get("taskListId") != list_id:
                       continue
   ```
   Note: move the `_resolve_list_name` call outside the loop for efficiency — resolve once before the loop and filter by ID.

   Better pattern:
   ```python
           # Resolve list filter
           list_id_filter: str | None = None
           if list_name:
               list_id_filter = _resolve_list_name(client, list_name)
   ```
   Then in the loop:
   ```python
               if list_id_filter and t.get("taskListId") != list_id_filter:
                   continue
   ```

6. Also update the view commands (`today`, `this-week`, `this-month`) that call `enrich_tasks` — they need to pass `task_lists` too. Find all `enrich_tasks(` calls in cli.py and add `task_lists=all_task_lists` parameter. You'll need to fetch the task lists in those view commands:
   ```python
               all_task_lists = [tl.model_dump() for tl in client.list_task_lists()]
   ```
   Then pass to each `enrich_tasks` call.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_tasks.py::TestTasksListByList -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All pass (view commands still work with the new parameter)

**Step 6: Run mypy**

Run: `uv run mypy src/guten_morgen/cli.py src/guten_morgen/output.py`
Expected: clean

**Step 7: Commit**

```bash
git add src/guten_morgen/cli.py src/guten_morgen/output.py tests/test_cli_tasks.py
git commit -m "feat(cli): add --list filter on tasks list + list_name enrichment"
```

---

### Task 7: Update usage docstring + usage tests

**Files:**
- Modify: `src/guten_morgen/cli.py` (usage function)
- Modify: `tests/test_cli_usage.py`

**Step 1: Write the failing test**

In `tests/test_cli_usage.py`, add:

```python
    def test_contains_lists_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert result.exit_code == 0
        assert "gm lists list" in result.output
        assert "gm lists create" in result.output
        assert "gm lists update" in result.output
        assert "gm lists delete" in result.output
        assert "--list" in result.output
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_usage.py::TestUsage::test_contains_lists_commands -v`
Expected: FAIL

**Step 3: Update usage docstring**

In `src/guten_morgen/cli.py`, find the `usage()` function and its docstring. Add a new "### Lists" section after "### Tags":

```
### Lists (Task Lists)
- `gm lists list [--json]`
  List all task lists.

- `gm lists create --name TEXT [--color HEX]`
  Create a task list.

- `gm lists update ID [--name TEXT] [--color HEX]`
  Update a task list.

- `gm lists delete ID`
  Delete a task list.
```

Also update the Tasks section to mention `--list`:

- On `gm tasks list`, add `[--list NAME]` to the signature and a note: `--list filters by task list name (case-insensitive).`
- On `gm tasks create`, add `[--list NAME]` and note: `--list assigns to a task list by name.`
- On `gm tasks update`, add `[--list NAME]` and note: `--list moves task to a list by name.`

Update the enrichment description to include `list_name`:
```
Tasks are enriched with source, source_id, source_url, source_status, tag_names, list_name fields.
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_usage.py::TestUsage::test_contains_lists_commands -v`
Expected: PASS

**Step 5: Run full suite**

Run: `uv run pytest -x -q`
Expected: All pass

**Step 6: Run mypy**

Run: `uv run mypy src/`
Expected: clean

**Step 7: Commit**

```bash
git add src/guten_morgen/cli.py tests/test_cli_usage.py
git commit -m "docs: add task lists commands and --list option to usage"
```

---

### Task 8: Final verification

**Step 1: Full test suite with coverage**

Run: `uv run pytest -x -q --cov`
Expected: All pass, coverage >= 90%

**Step 2: Full mypy check**

Run: `uv run mypy src/`
Expected: clean

**Step 3: Update CLAUDE.md if needed**

Check if CLAUDE.md's agent startup commands or file map need updates. The file map in `CLAUDE.md` doesn't list individual CLI commands, so likely no change needed. But the `gm usage` output will auto-update since it's generated from the docstring.

**Step 4: Verify pre-commit hooks pass**

Run: `uv run pre-commit run --all-files`
Expected: All pass
