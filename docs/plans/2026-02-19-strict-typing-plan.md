# Strict Typing (Pydantic v2) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace TypedDicts with Pydantic v2 models for runtime validation, typed client signatures, and API drift detection.

**Architecture:** Client methods return Pydantic models validated at parse time. CLI layer calls `.model_dump()` immediately after client calls, then passes dicts to enrichment/output (unchanged). Cache stores raw dicts; validation happens on cache miss and on cache-hit retrieval.

**Tech Stack:** Pydantic v2, mypy strict, ruff (existing + TC/ANN rules)

**Key insight:** The existing TypedDicts are out of sync with the actual API (e.g., Account TypedDict has `accountId` but API returns `id`). Models must match the ACTUAL API fields as reflected in test fixtures, not the old TypedDicts.

---

### Task 1: Add Pydantic dependency + MorgenModel base class

**Files:**
- Modify: `pyproject.toml:6-7` (add pydantic dep)
- Modify: `src/morgen/models.py` (add base class, keep existing TypedDicts temporarily)

**Step 1: Add pydantic to dependencies**

In `pyproject.toml`, add `pydantic>=2.0` to `dependencies`:

```toml
dependencies = [
    "click>=8.1",
    "httpx>=0.27",
    "pydantic>=2.0",
    "rich>=13.0",
    "jq>=1.8",
    "python-dotenv>=1.0",
    "tomli>=2.0; python_version < '3.11'",
]
```

**Step 2: Install**

Run: `uv sync --all-extras`

**Step 3: Add MorgenModel base class to models.py**

Add at the top of `models.py`, after imports:

```python
from pydantic import BaseModel, ConfigDict

class MorgenModel(BaseModel):
    """Base model for all Morgen API objects.

    - extra="ignore": resilient to API additions (new fields don't break us)
    - populate_by_name=True: allows both alias and field name for construction
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
```

Keep existing TypedDicts below — they'll be replaced one at a time.

**Step 4: Verify**

Run: `uv run mypy src/ && uv run pytest -x -q`
Expected: All pass (no behavior change)

**Step 5: Commit**

```bash
git add pyproject.toml src/morgen/models.py uv.lock
git commit -m "feat: add pydantic dep and MorgenModel base class"
```

---

### Task 2: Migrate Tag model (proves the pattern)

Tag is the simplest model (3 fields). This task establishes the full migration pattern: model, client, CLI, tests.

**Files:**
- Modify: `src/morgen/models.py` (replace Tag TypedDict)
- Modify: `src/morgen/client.py:28-64,437-473` (generic extractors + tag methods)
- Modify: `src/morgen/cli.py:479-483,991-1070` (tag commands)
- Modify: `tests/conftest.py` (no changes needed — mock transport returns JSON)
- Modify: `tests/test_cli_tags.py` (may need minor adjustments)

**Step 1: Write test for Pydantic Tag model**

Create `tests/test_models.py`:

```python
"""Tests for Pydantic models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from morgen.models import Tag


class TestTagModel:
    def test_valid_tag(self) -> None:
        tag = Tag(id="tag-1", name="urgent", color="#ff0000")
        assert tag.id == "tag-1"
        assert tag.name == "urgent"
        assert tag.color == "#ff0000"

    def test_optional_color(self) -> None:
        tag = Tag(id="tag-1", name="urgent")
        assert tag.color is None

    def test_extra_fields_ignored(self) -> None:
        tag = Tag(id="tag-1", name="urgent", unknown_field="whatever")
        assert not hasattr(tag, "unknown_field")

    def test_model_dump_roundtrip(self) -> None:
        tag = Tag(id="tag-1", name="urgent", color="#ff0000")
        d = tag.model_dump()
        assert d == {"id": "tag-1", "name": "urgent", "color": "#ff0000"}

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            Tag(id="tag-1")  # missing name
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `Tag` is still a TypedDict, not a BaseModel

**Step 3: Replace Tag TypedDict with Pydantic model**

In `models.py`, replace:

```python
class Tag(TypedDict, total=False):
    """Tag for tasks."""
    id: str
    name: str
    color: str
```

With:

```python
class Tag(MorgenModel):
    """Tag for tasks."""
    id: str
    name: str
    color: str | None = None
```

**Step 4: Run model test**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS

**Step 5: Make `_extract_list` and `_extract_single` generic**

In `client.py`, add imports and create generic versions alongside the existing ones:

```python
from typing import Any, TypeVar, cast, overload
from morgen.models import MorgenModel

T = TypeVar("T", bound=MorgenModel)

def _extract_list_typed(data: Any, key: str, model: type[T]) -> list[T]:
    """Extract and validate a list from Morgen's nested response format."""
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        inner = data.get("data", data)
        if isinstance(inner, dict):
            raw = inner.get(key, [])
        elif isinstance(inner, list):
            raw = inner
        else:
            raw = []
    else:
        raw = []
    return [model.model_validate(item) for item in raw]


def _extract_single_typed(data: Any, key: str, model: type[T]) -> T:
    """Extract and validate a single item from Morgen's nested response format."""
    if data is None:
        return model.model_validate({})
    if isinstance(data, dict):
        inner = data.get("data", data)
        if isinstance(inner, dict):
            if key in inner:
                return model.model_validate(inner[key])
            return model.model_validate(inner)
        return model.model_validate(data)
    return model.model_validate(data)
```

Keep the old `_extract_list` and `_extract_single` — they'll be removed once all models are migrated.

**Step 6: Update client tag methods**

Replace the tag methods in `client.py`:

```python
# ----- Tags -----

def list_tags(self) -> list[Tag]:
    """List all tags."""
    cached = self._cache_get("tags")
    if cached is not None:
        return [Tag.model_validate(t) for t in cast(list[dict[str, Any]], cached)]
    data = self._request("GET", "/tags/list")
    result = _extract_list_typed(data, "tags", Tag)
    self._cache_set("tags", [t.model_dump() for t in result], TTL_TAGS)
    return result

def get_tag(self, tag_id: str) -> Tag:
    """Get a single tag."""
    key = f"tags/{tag_id}"
    cached = self._cache_get(key)
    if cached is not None:
        return Tag.model_validate(cast(dict[str, Any], cached))
    data = self._request("GET", "/tags/", params={"id": tag_id})
    result = _extract_single_typed(data, "tag", Tag)
    self._cache_set(key, result.model_dump(), TTL_SINGLE)
    return result

def create_tag(self, tag_data: dict[str, Any]) -> Tag:
    """Create a tag."""
    data = self._request("POST", "/tags/create", json=tag_data)
    self._cache_invalidate("tags")
    return _extract_single_typed(data, "tag", Tag)

def update_tag(self, tag_data: dict[str, Any]) -> Tag:
    """Update a tag."""
    data = self._request("POST", "/tags/update", json=tag_data)
    self._cache_invalidate("tags")
    return _extract_single_typed(data, "tag", Tag)

def delete_tag(self, tag_id: str) -> None:
    """Delete a tag."""
    self._request("POST", "/tags/delete", json={"id": tag_id})
    self._cache_invalidate("tags")
```

Add import at top of client.py:
```python
from morgen.models import Tag
```

**Step 7: Update CLI tag commands**

In `cli.py`, update tag commands to call `.model_dump()`:

`_resolve_tag_names` (line ~479):
```python
def _resolve_tag_names(client: MorgenClient, names: tuple[str, ...]) -> list[str]:
    """Resolve tag names to IDs. Case-insensitive matching."""
    all_tags = client.list_tags()
    name_to_id = {t.name.lower(): t.id for t in all_tags}
    return [name_to_id[n.lower()] for n in names if n.lower() in name_to_id]
```

`tags_list` command: change `data = client.list_tags()` to:
```python
data = [t.model_dump() for t in client.list_tags()]
```

`tags_get` command: change `data = client.get_tag(tag_id)` to:
```python
data = client.get_tag(tag_id).model_dump()
```

`tags_create`: change `result = client.create_tag(tag_data)` output to:
```python
result = client.create_tag(tag_data)
click.echo(json.dumps(result.model_dump(), indent=2, default=str, ensure_ascii=False))
```

`tags_update`: same pattern with `.model_dump()`.

**Step 8: Verify everything passes**

Run: `uv run mypy src/ && uv run pytest -x -q`
Expected: All pass

**Step 9: Commit**

```bash
git add src/morgen/models.py src/morgen/client.py src/morgen/cli.py tests/test_models.py
git commit -m "feat: migrate Tag to Pydantic model with runtime validation"
```

---

### Task 3: Migrate Account + Calendar models

**Files:**
- Modify: `src/morgen/models.py`
- Modify: `src/morgen/client.py:131-161` (account + calendar methods)
- Modify: `src/morgen/cli.py:395-428,486-512` (account/calendar commands + _auto_discover)
- Modify: `tests/test_models.py` (add model tests)

**Step 1: Add model tests to `tests/test_models.py`**

```python
from morgen.models import Account, Calendar

class TestAccountModel:
    def test_valid_account(self) -> None:
        acc = Account(id="acc-1", name="Work", integrationGroups=["calendars"])
        assert acc.id == "acc-1"
        assert acc.integrationGroups == ["calendars"]

    def test_defaults(self) -> None:
        acc = Account(id="acc-1")
        assert acc.integrationGroups == []
        assert acc.name is None

    def test_extra_ignored(self) -> None:
        acc = Account(id="acc-1", someFutureField="x")
        assert not hasattr(acc, "someFutureField")

class TestCalendarModel:
    def test_valid_calendar(self) -> None:
        cal = Calendar(id="cal-1", accountId="acc-1", name="Work")
        assert cal.name == "Work"

    def test_myRights_can_be_dict_or_string(self) -> None:
        cal1 = Calendar(id="c1", myRights={"mayWriteAll": True})
        cal2 = Calendar(id="c2", myRights="rw")
        assert cal1.myRights == {"mayWriteAll": True}
        assert cal2.myRights == "rw"
```

**Step 2: Run test, verify fail, then implement**

Replace TypedDicts in `models.py`:

```python
class Account(MorgenModel):
    """Connected calendar account."""
    id: str
    name: str | None = None
    providerUserDisplayName: str | None = None
    preferredEmail: str | None = None
    integrationId: str | None = None
    integrationGroups: list[str] = []
    providerId: str | None = None
    providerAccountId: str | None = None
    email: str | None = None

class Calendar(MorgenModel):
    """Calendar within an account."""
    id: str
    calendarId: str | None = None
    accountId: str | None = None
    name: str | None = None
    color: str | None = None
    writable: bool | None = None
    isActiveByDefault: bool | None = None
    myRights: Any = None  # Can be dict or string depending on provider
```

**Step 3: Update client methods**

`list_accounts()` → returns `list[Account]`
`list_task_accounts()` → returns `list[Account]`
`list_calendars()` → returns `list[Calendar]`

Add imports: `from morgen.models import Account, Calendar, Tag`

Update `list_all_events()` internal code to use model attributes instead of `.get()`:
```python
# Before: if "calendars" in account.get("integrationGroups", []):
# After:  if "calendars" in account.integrationGroups:
# (because integrationGroups defaults to [])

# Before: aid = account.get("id", "")
# After:  aid = account.id

# Before: cid = cal.get("id", cal.get("calendarId", ""))
# After:  cid = cal.id or cal.calendarId or ""

# Before: aid = cal.get("accountId", "")
# After:  aid = cal.accountId or ""
```

**Step 4: Update CLI**

In `cli.py`:
- `accounts` command: `data = [a.model_dump() for a in client.list_accounts()]`
- `calendars` command: `data = [c.model_dump() for c in client.list_calendars()]`
- `_auto_discover()`: Use model attributes for filtering, then convert at the end:
  ```python
  accounts_data = client.list_accounts()
  calendar_accounts = [a for a in accounts_data if "calendars" in a.integrationGroups]
  account = calendar_accounts[0] if calendar_accounts else accounts_data[0]
  account_id = account.id

  calendars_data = client.list_calendars()
  account_cals = [c for c in calendars_data if c.accountId == account_id]
  writable = [c.id for c in account_cals if _is_writable(c.model_dump())]
  ```
- `_is_writable()`: Takes a dict (from model_dump), no change needed. Or update to accept Calendar model.

**Step 5: Verify + commit**

Run: `uv run mypy src/ && uv run pytest -x -q`

```bash
git add src/morgen/models.py src/morgen/client.py src/morgen/cli.py tests/test_models.py
git commit -m "feat: migrate Account and Calendar to Pydantic models"
```

---

### Task 4: Migrate Task + TaskListResponse (most complex)

**Files:**
- Modify: `src/morgen/models.py`
- Modify: `src/morgen/client.py:267-390` (all task methods)
- Modify: `src/morgen/cli.py:660-975` (task commands)
- Modify: `tests/test_models.py`

**Step 1: Add model tests**

```python
from morgen.models import Task, LabelDef, Space, TaskListResponse

class TestTaskModel:
    def test_valid_task(self) -> None:
        task = Task(id="task-1", title="Review PR", priority=2, tags=["tag-1"])
        assert task.id == "task-1"
        assert task.tags == ["tag-1"]

    def test_integration_id_defaults_to_morgen(self) -> None:
        task = Task(id="t1", title="Test")
        assert task.integrationId == "morgen"

    def test_external_task_with_labels_and_links(self) -> None:
        task = Task(
            id="linear-1",
            title="Budget",
            integrationId="linear",
            labels=[{"id": "state", "value": "in-progress"}],
            links={"original": {"href": "https://linear.app/...", "title": "Open"}},
        )
        assert task.integrationId == "linear"
        assert len(task.labels) == 1

    def test_model_dump_preserves_camelCase(self) -> None:
        task = Task(id="t1", title="Test", taskListId="inbox", integrationId="linear")
        d = task.model_dump()
        assert "taskListId" in d
        assert "integrationId" in d

class TestTaskListResponse:
    def test_empty_response(self) -> None:
        resp = TaskListResponse()
        assert resp.tasks == []
        assert resp.labelDefs == []
        assert resp.spaces == []

    def test_with_data(self) -> None:
        resp = TaskListResponse(
            tasks=[Task(id="t1", title="Test")],
            labelDefs=[LabelDef(id="state", label="Status", type="enum", values=[])],
            spaces=[Space(id="s1", name="Projects")],
        )
        assert len(resp.tasks) == 1
        assert resp.labelDefs[0].label == "Status"
```

**Step 2: Implement models**

In `models.py`:

```python
class LabelDef(MorgenModel):
    """Label definition from task list response (external integrations)."""
    id: str
    label: str | None = None
    type: str | None = None
    values: list[dict[str, Any]] = []

class Space(MorgenModel):
    """Space/project from task list response (external integrations)."""
    id: str
    name: str | None = None

class Task(MorgenModel):
    """Task item."""
    id: str
    title: str = ""
    description: str | None = None
    progress: str | None = None
    status: str | None = None
    priority: int | None = None
    due: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    completedAt: str | None = None
    parentId: str | None = None
    tags: list[str] = []
    taskListId: str | None = None
    estimatedDuration: str | None = None
    integrationId: str = "morgen"
    accountId: str | None = None
    labels: list[dict[str, Any]] = []
    links: dict[str, Any] = {}

class TaskListResponse(MorgenModel):
    """Compound response from list_all_tasks."""
    tasks: list[Task] = []
    labelDefs: list[LabelDef] = []
    spaces: list[Space] = []
```

**Step 3: Update client task methods**

Key changes:

`list_all_tasks()` → returns `TaskListResponse`:
```python
def list_all_tasks(self, *, source: str | None = None, limit: int = 100) -> TaskListResponse:
    all_tasks_raw: list[dict[str, Any]] = []
    all_label_defs_raw: list[dict[str, Any]] = []
    all_spaces_raw: list[dict[str, Any]] = []

    # Morgen-native tasks (no setdefault needed — Task model defaults integrationId="morgen")
    if source is None or source == "morgen":
        data = self._request("GET", "/tasks/list", params={"limit": limit})
        all_tasks_raw.extend(_extract_list(data, "tasks"))

    # External sources (same as before, gather raw dicts)
    task_accounts = self.list_task_accounts()
    for account in task_accounts:
        integration = account.integrationId or ""
        if source is not None and integration != source:
            continue
        account_id = account.id
        if not account_id:
            continue
        # ... cache logic same as before, gather into all_*_raw lists ...

    return TaskListResponse(
        tasks=[Task.model_validate(t) for t in all_tasks_raw],
        labelDefs=[LabelDef.model_validate(ld) for ld in all_label_defs_raw],
        spaces=[Space.model_validate(s) for s in all_spaces_raw],
    )
```

Other task methods get typed returns:
- `list_tasks()` → `list[Task]`
- `get_task()` → `Task`
- `create_task()` → `Task`
- `update_task()` → `Task`
- `close_task()` → `Task`
- `reopen_task()` → `Task`
- `move_task()` → `Task`
- `schedule_task()` — calls `self.get_task()` which now returns `Task`, access attributes instead of `.get()`:
  ```python
  task = self.get_task(task_id)
  title = task.title or "Untitled task"
  duration = f"PT{duration_minutes}M" if duration_minutes else (task.estimatedDuration or "PT30M")
  ```

**Step 4: Update CLI task commands**

In `tasks_list`:
```python
result = client.list_all_tasks(source=source, limit=limit)
data = [t.model_dump() for t in result.tasks]
label_defs = [ld.model_dump() for ld in result.labelDefs]
```
Then enrichment + filtering stays dict-based (unchanged).

In `tasks_get`:
```python
data = client.get_task(task_id).model_dump()
```

In `tasks_create`, `tasks_close`, `tasks_reopen`, `tasks_move`:
```python
result = client.create_task(task_data)  # returns Task
click.echo(json.dumps(result.model_dump(), indent=2, ...))
```

In `tasks_update` — handle the `result or {...}` fallback:
```python
result = client.update_task(task_data)
click.echo(json.dumps(result.model_dump(), indent=2, ...))
```
Note: `_extract_single_typed` always returns a model (may be empty), so the `or` fallback isn't needed.

In `_combined_view`:
```python
tasks_result = client.list_all_tasks()
all_tags_models = client.list_tags()
all_tags = [t.model_dump() for t in all_tags_models]
tasks_data = enrich_tasks(
    [t.model_dump() for t in tasks_result.tasks],
    label_defs=[ld.model_dump() for ld in tasks_result.labelDefs],
    tags=all_tags,
)
```

In `usage` command's dynamic task source discovery:
```python
task_accounts = client.list_task_accounts()
for acc in task_accounts:
    name = acc.providerUserDisplayName or ""
    iid = acc.integrationId or ""
```

**Step 5: Verify + commit**

Run: `uv run mypy src/ && uv run pytest -x -q`

```bash
git add src/morgen/models.py src/morgen/client.py src/morgen/cli.py tests/test_models.py
git commit -m "feat: migrate Task and TaskListResponse to Pydantic models"
```

---

### Task 5: Migrate Event model

**Files:**
- Modify: `src/morgen/models.py`
- Modify: `src/morgen/client.py:165-263` (event methods)
- Modify: `src/morgen/cli.py:439-657` (event commands)
- Modify: `tests/test_models.py`

**Step 1: Add model tests**

```python
from pydantic import Field
from morgen.models import Event

class TestEventModel:
    def test_valid_event(self) -> None:
        event = Event(id="evt-1", title="Standup", start="2026-02-17T09:00:00")
        assert event.title == "Standup"

    def test_morgen_metadata_alias(self) -> None:
        """morgen.so:metadata field has a dot — must use alias."""
        event = Event.model_validate({
            "id": "evt-1",
            "title": "Frame",
            "morgen.so:metadata": {"frameFilterMql": "{}"},
        })
        assert event.morgen_metadata is not None
        assert "frameFilterMql" in event.morgen_metadata

    def test_model_dump_by_alias_preserves_metadata_key(self) -> None:
        event = Event.model_validate({
            "id": "evt-1",
            "morgen.so:metadata": {"frameFilterMql": "{}"},
        })
        d = event.model_dump(by_alias=True)
        assert "morgen.so:metadata" in d

    def test_participants_and_locations(self) -> None:
        event = Event(
            id="evt-1",
            participants={"p1": {"name": "Alice"}},
            locations={"loc1": {"name": "Room 42"}},
        )
        assert "p1" in event.participants
```

**Step 2: Implement Event model**

In `models.py`:

```python
from pydantic import BaseModel, ConfigDict, Field

class Event(MorgenModel):
    """Calendar event."""
    id: str
    title: str | None = None
    description: str | None = None
    start: str | None = None
    end: str | None = None
    duration: str | None = None
    calendarId: str | None = None
    accountId: str | None = None
    participants: dict[str, Any] | None = None
    locations: dict[str, Any] | None = None
    showAs: str | None = None
    showWithoutTime: bool | None = None
    timeZone: str | None = None
    morgen_metadata: dict[str, Any] | None = Field(None, alias="morgen.so:metadata")
```

**Step 3: Update client event methods**

- `list_events()` → `list[Event]`
- `list_all_events()` → `list[Event]` (uses list_events internally, already returns Event models; attribute access for filtering)
- `create_event()` → `Event`
- `update_event()` → `Event`

In `list_all_events`, internal dict access becomes attribute access:
```python
# Before: if "(via Morgen)" not in e.get("title", "")
# After:  if "(via Morgen)" not in (e.title or "")
```

**Step 4: Update CLI event commands**

In `events_list`:
```python
if account_id and calendar_ids_str:
    data_models = client.list_events(account_id, cal_ids, start, end)
else:
    data_models = client.list_all_events(start, end, **_filter_kwargs(cf))
data = [e.model_dump(by_alias=True) for e in data_models]
# _is_frame_event and enrich_events work on dicts — unchanged
```

**Important:** Use `model_dump(by_alias=True)` for Event so `morgen.so:metadata` key is preserved in the dict for `_is_frame_event`.

In `events_create`, `events_update`:
```python
result = client.create_event(event_data)
click.echo(json.dumps(result.model_dump(by_alias=True), indent=2, ...))
```

In `_combined_view`:
```python
events_data = client.list_all_events(start, end, **_filter_kwargs(cf))
events_list_raw = [e.model_dump(by_alias=True) for e in events_data]
```

In `next` command:
```python
events_data = client.list_all_events(...)
upcoming = [e for e in events_data if (e.start or "") >= now.isoformat()[:19]]
# ... filter, sort using model attributes ...
upcoming_dicts = [e.model_dump(by_alias=True) for e in upcoming]
```
Note: sorting and filtering in `next` uses `e.get("start", "")` — change to `e.start or ""`.

**Step 5: Verify + commit**

Run: `uv run mypy src/ && uv run pytest -x -q`

```bash
git add src/morgen/models.py src/morgen/client.py src/morgen/cli.py tests/test_models.py
git commit -m "feat: migrate Event to Pydantic model with alias for metadata"
```

---

### Task 6: Clean up — remove old extractors and TypedDict remnants

**Files:**
- Modify: `src/morgen/models.py` (remove TypedDict import if unused)
- Modify: `src/morgen/client.py` (remove old `_extract_list`, `_extract_single`, rename `_typed` variants)

**Step 1: Remove old extractors**

Delete `_extract_list()` and `_extract_single()` (the untyped versions). Rename `_extract_list_typed` → `_extract_list` and `_extract_single_typed` → `_extract_single`.

**Step 2: Remove unused TypedDict import**

In `models.py`, remove `from typing import TypedDict` if no TypedDicts remain.

**Step 3: Verify + commit**

Run: `uv run mypy src/ && uv run pytest -x -q`

```bash
git add src/morgen/models.py src/morgen/client.py
git commit -m "refactor: remove legacy TypedDict extractors"
```

---

### Task 7: API drift detection tests

**Files:**
- Create: `tests/fixtures/` directory
- Create: `tests/fixtures/account_sample.json`
- Create: `tests/fixtures/calendar_sample.json`
- Create: `tests/fixtures/event_sample.json`
- Create: `tests/fixtures/task_sample.json`
- Create: `tests/fixtures/tag_sample.json`
- Modify: `tests/test_models.py` (add drift tests)

**Step 1: Create fixture files from test fake data**

Extract representative samples from `conftest.py` fake data into JSON fixtures. These represent the "known API contract."

`tests/fixtures/account_sample.json`:
```json
{
  "id": "acc-1",
  "name": "Work Google",
  "providerUserDisplayName": "Test User",
  "preferredEmail": "test@example.com",
  "integrationId": "google",
  "integrationGroups": ["calendars"]
}
```

(Same pattern for other models — one JSON file per model with a real-looking sample.)

**Step 2: Write drift detection test**

In `tests/test_models.py`:

```python
import json
from pathlib import Path

from morgen.models import Account, Calendar, Event, Tag, Task

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.mark.parametrize("model,fixture_file", [
    (Account, "account_sample.json"),
    (Calendar, "calendar_sample.json"),
    (Event, "event_sample.json"),
    (Task, "task_sample.json"),
    (Tag, "tag_sample.json"),
])
def test_model_covers_api_fields(model: type, fixture_file: str) -> None:
    """Detect when the API returns fields we haven't modeled.

    Fails when a fixture has fields not in the model. To fix:
    1. Add the new field to the model
    2. Or confirm it's intentionally ignored and remove from fixture
    """
    fixture_path = FIXTURES / fixture_file
    sample = json.loads(fixture_path.read_text())
    model_fields = set(model.model_fields.keys())

    # Check aliases too (e.g., morgen_metadata -> morgen.so:metadata)
    for field_name, field_info in model.model_fields.items():
        if field_info.alias:
            model_fields.add(field_info.alias)

    api_fields = set(sample.keys())
    new_fields = api_fields - model_fields
    assert not new_fields, (
        f"{model.__name__} doesn't model these API fields: {new_fields}. "
        f"Add them to the model or remove from fixture if intentionally ignored."
    )
```

**Step 3: Verify + commit**

Run: `uv run pytest tests/test_models.py -v`

```bash
git add tests/fixtures/ tests/test_models.py
git commit -m "test: add API drift detection for Pydantic models"
```

---

### Task 8: Add ruff typing rules

**Files:**
- Modify: `pyproject.toml:44-45` (add ruff rules)

**Step 1: Enable TC and ANN rules**

In `pyproject.toml`, update ruff lint config:

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "W", "UP", "TC", "ANN"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["ANN"]  # Don't require annotations in tests (pytest fixtures)
```

- **TC** (flake8-type-checking): Catches imports that should be under `TYPE_CHECKING`
- **ANN** (flake8-annotations): Enforces type annotations on all public functions

**Step 2: Fix violations**

Run: `uv run ruff check .`

Fix any new violations. Common ones:
- Move imports used only in annotations under `if TYPE_CHECKING:`
- Add missing return type annotations (should be few given current coverage)

**Step 3: Verify + commit**

Run: `uv run ruff check . && uv run mypy src/ && uv run pytest -x -q`

```bash
git add pyproject.toml src/
git commit -m "chore: enable ruff TC + ANN rules for type enforcement"
```

---

## Summary of changes per file

| File | Changes |
|------|---------|
| `pyproject.toml` | Add pydantic dep, ruff TC/ANN rules |
| `src/morgen/models.py` | Replace 5 TypedDicts with Pydantic models, add MorgenModel base, LabelDef, Space, TaskListResponse |
| `src/morgen/client.py` | Generic typed extractors, all methods return Pydantic models, attribute access in internal methods |
| `src/morgen/cli.py` | Add `.model_dump()` calls after client methods, attribute access in _auto_discover/_resolve_tag_names |
| `src/morgen/output.py` | **No changes** (stays dict-based) |
| `tests/test_models.py` | New: model validation tests + drift detection |
| `tests/fixtures/*.json` | New: API response samples for drift detection |
| `tests/conftest.py` | Minimal changes (mock transport stays dict-based) |
