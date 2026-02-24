# Missing Task Fields & Markdown Descriptions — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `position`, `earliestStart`, `descriptionContentType` to Task model, add `--earliest-start` CLI option, fix priority range to 0-9, and transparently convert descriptions between markdown (CLI) and HTML (API).

**Architecture:** New `markup.py` module for md↔html conversion. Model gets three new fields. CLI gets `--earliest-start` on create/update, priority range fix. `enrich_tasks()` converts HTML descriptions to markdown on read. Write path converts markdown to HTML before API call.

**Tech Stack:** Python 3.10+, Pydantic v2, Click, `markdownify` (html→md), `markdown` (md→html), pytest

---

### Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml:23-30`

**Step 1: Add markdownify and markdown to dependencies**

In `pyproject.toml`, add to the `dependencies` list (after `"tomli>=2.0; python_version < '3.11'"`):

```toml
    "markdownify>=0.14",
    "markdown>=3.7",
```

**Step 2: Sync**

Run: `uv sync --all-extras`
Expected: resolves and installs both packages

**Step 3: Verify imports work**

Run: `uv run python3 -c "import markdownify; import markdown; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add markdownify and markdown dependencies"
```

---

### Task 2: Create `markup.py` module

**Files:**
- Create: `src/guten_morgen/markup.py`
- Create: `tests/test_markup.py`

**Step 1: Write the failing tests**

Create `tests/test_markup.py`:

```python
"""Tests for markup conversion."""

from __future__ import annotations

from guten_morgen.markup import html_to_markdown, markdown_to_html


class TestHtmlToMarkdown:
    def test_converts_bullet_list(self) -> None:
        html = "<ul><li><p>bullet one</p></li><li><p>bullet two</p></li></ul>"
        result = html_to_markdown(html)
        assert "bullet one" in result
        assert "bullet two" in result
        # Should use markdown list syntax
        assert "* " in result or "- " in result

    def test_converts_bold(self) -> None:
        html = "<p><strong>bold text</strong></p>"
        result = html_to_markdown(html)
        assert "**bold text**" in result

    def test_converts_paragraph(self) -> None:
        html = "<p>normal text</p>"
        result = html_to_markdown(html)
        assert "normal text" in result
        assert "<p>" not in result

    def test_plain_text_passthrough(self) -> None:
        """Plain text with no HTML tags passes through unchanged."""
        text = "Just a plain note with no formatting"
        result = html_to_markdown(text)
        assert result == text

    def test_none_returns_none(self) -> None:
        result = html_to_markdown(None)
        assert result is None

    def test_empty_string(self) -> None:
        result = html_to_markdown("")
        assert result == ""


class TestMarkdownToHtml:
    def test_converts_bullet_list(self) -> None:
        md = "- item one\n- item two"
        result = markdown_to_html(md)
        assert "<li>" in result
        assert "item one" in result

    def test_converts_bold(self) -> None:
        md = "**bold text**"
        result = markdown_to_html(md)
        assert "<strong>bold text</strong>" in result

    def test_plain_text_wraps_in_p(self) -> None:
        md = "Just plain text"
        result = markdown_to_html(md)
        assert "Just plain text" in result

    def test_none_returns_none(self) -> None:
        result = markdown_to_html(None)
        assert result is None

    def test_empty_string(self) -> None:
        result = markdown_to_html("")
        assert result == ""
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_markup.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

**Step 3: Write minimal implementation**

Create `src/guten_morgen/markup.py`:

```python
"""Transparent markdown ↔ HTML conversion for task descriptions.

The Morgen API stores descriptions as HTML but agents work with markdown.
This module converts transparently in both directions.
"""

from __future__ import annotations

import re


def _is_html(text: str) -> bool:
    """Check if text contains HTML tags."""
    return bool(re.search(r"<[a-zA-Z][^>]*>", text))


def html_to_markdown(html: str | None) -> str | None:
    """Convert HTML to markdown. Plain text passes through unchanged."""
    if html is None:
        return None
    if not html:
        return ""
    if not _is_html(html):
        return html
    import markdownify  # type: ignore[import-untyped]

    result: str = markdownify.markdownify(html, strip=["img"])
    return result.strip()


def markdown_to_html(md: str | None) -> str | None:
    """Convert markdown to HTML."""
    if md is None:
        return None
    if not md:
        return ""
    import markdown as md_lib

    return md_lib.markdown(md)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_markup.py -v`
Expected: PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/markup.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/guten_morgen/markup.py tests/test_markup.py
git commit -m "feat: add markup module for markdown/HTML conversion"
```

---

### Task 3: Add new fields to Task model

**Files:**
- Modify: `src/guten_morgen/models.py:83-104`
- Modify: `tests/test_models.py`

**Step 1: Write the failing tests**

In `tests/test_models.py`, add to the existing `TestTask` class (or create a new `TestTaskNewFields` class):

```python
class TestTaskNewFields:
    def test_position_field(self) -> None:
        data = {"id": "t1", "title": "Test", "position": 1771922554998}
        task = Task.model_validate(data)
        assert task.position == 1771922554998

    def test_earliest_start_field(self) -> None:
        data = {"id": "t1", "title": "Test", "earliestStart": "2026-02-25T00:00:00"}
        task = Task.model_validate(data)
        assert task.earliestStart == "2026-02-25T00:00:00"

    def test_description_content_type_field(self) -> None:
        data = {"id": "t1", "title": "Test", "descriptionContentType": "text/plain"}
        task = Task.model_validate(data)
        assert task.descriptionContentType == "text/plain"

    def test_fields_optional_default_none(self) -> None:
        data = {"id": "t1", "title": "Test"}
        task = Task.model_validate(data)
        assert task.position is None
        assert task.earliestStart is None
        assert task.descriptionContentType is None

    def test_full_api_response(self) -> None:
        """Real API response shape from Morgen v3."""
        data = {
            "@type": "Task",
            "id": "548211d9-8b34-4265-ada9-575b22769d30",
            "taskListId": "inbox",
            "tags": [],
            "title": "Test for gm1",
            "description": "<ul><li><p>bullet</p></li></ul><p></p>",
            "descriptionContentType": "text/plain",
            "estimatedDuration": "PT60M",
            "priority": 1,
            "progress": "needs-action",
            "earliestStart": "2026-02-25T00:00:00",
            "position": 1771922554998,
            "created": "2026-02-24T08:42:41Z",
            "updated": "2026-02-24T08:43:14.547Z",
            "integrationId": "morgen",
        }
        task = Task.model_validate(data)
        assert task.position == 1771922554998
        assert task.earliestStart == "2026-02-25T00:00:00"
        assert task.descriptionContentType == "text/plain"

    def test_priority_range_nine(self) -> None:
        """API supports priority 0-9, not just 0-4."""
        data = {"id": "t1", "title": "Test", "priority": 9}
        task = Task.model_validate(data)
        assert task.priority == 9
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_models.py::TestTaskNewFields -v`
Expected: FAIL with `AttributeError` (fields don't exist yet)

**Step 3: Write minimal implementation**

In `src/guten_morgen/models.py`, add three fields to the `Task` class after `occurrenceStart` (line 104):

```python
    position: int | None = None
    earliestStart: str | None = None
    descriptionContentType: str | None = None
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py::TestTaskNewFields -v`
Expected: PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/models.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/guten_morgen/models.py tests/test_models.py
git commit -m "feat(models): add position, earliestStart, descriptionContentType to Task"
```

---

### Task 4: Add `--earliest-start` to CLI + priority range fix

**Files:**
- Modify: `src/guten_morgen/cli.py:1137-1218`
- Modify: `tests/test_cli_tasks.py`

**Step 1: Write the failing tests**

In `tests/test_cli_tasks.py`, add:

```python
class TestTasksCreateWithEarliestStart:
    def test_create_with_earliest_start_date(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "create", "--title", "New task", "--earliest-start", "2026-03-01"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("earliestStart") is not None

    def test_create_with_earliest_start_datetime(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "create", "--title", "New task", "--earliest-start", "2026-03-01T09:00:00"])
        assert result.exit_code == 0


class TestTasksUpdateWithEarliestStart:
    def test_update_with_earliest_start(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "update", "task-1", "--earliest-start", "2026-03-15"])
        assert result.exit_code == 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_tasks.py::TestTasksCreateWithEarliestStart -v`
Expected: FAIL with `no such option: --earliest-start`

**Step 3: Write minimal implementation**

In `src/guten_morgen/cli.py`:

1. Add a `_normalize_earliest_start` helper near `_normalize_due` (around line 616). It uses the same logic: date-only appends `T00:00:00`, strips trailing `Z`:

```python
def _normalize_earliest_start(val: str) -> str:
    """Normalize earliest start to 19-char ISO 8601 (YYYY-MM-DDTHH:MM:SS).

    Same normalization as _normalize_due but date-only defaults to T00:00:00.
    """
    if val.endswith("Z"):
        val = val[:-1]
    if "+" in val[10:]:
        val = val[: val.index("+", 10)]
    if len(val) == 10:
        val += "T00:00:00"
    return val[:19]
```

2. Add `--earliest-start` option to `tasks_create` (after `--list` option, around line 1144):

```python
@click.option("--earliest-start", default=None, help="Earliest start datetime (ISO 8601).")
```

Add `earliest_start: str | None,` to the function signature.

Add in the body (after the `list_name` block):

```python
        if earliest_start:
            task_data["earliestStart"] = _normalize_earliest_start(earliest_start)
```

3. Same for `tasks_update` — add the option, parameter, and body logic.

4. Fix priority help text: change `"Priority (0-4)."` to `"Priority (0-9)."` on both create and update.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_tasks.py::TestTasksCreateWithEarliestStart tests/test_cli_tasks.py::TestTasksUpdateWithEarliestStart -v`
Expected: PASS

**Step 5: Run full suite + mypy**

Run: `uv run pytest -x -q && uv run mypy src/`
Expected: All pass, clean

**Step 6: Commit**

```bash
git add src/guten_morgen/cli.py tests/test_cli_tasks.py
git commit -m "feat(cli): add --earliest-start option and fix priority range to 0-9"
```

---

### Task 5: Markdown conversion in enrichment (read path)

**Files:**
- Modify: `src/guten_morgen/output.py:179-227`
- Modify: `tests/conftest.py` (add HTML descriptions to FAKE_TASKS)
- Modify: `tests/test_cli_tasks.py`

**Step 1: Update fake data**

In `tests/conftest.py`, update `FAKE_TASKS` to include HTML descriptions and new fields on some tasks. Add to `task-1`:

```python
    "description": "<ul><li><p>check tests</p></li><li><p>review code</p></li></ul>",
    "descriptionContentType": "text/plain",
    "position": 1771922554998,
    "earliestStart": "2026-02-25T00:00:00",
```

Add to `task-2`:

```python
    "description": "Plain text note, no formatting",
    "position": 1771922636033,
```

**Step 2: Write the failing tests**

In `tests/test_cli_tasks.py`, add:

```python
class TestTaskDescriptionMarkdown:
    def test_html_description_converted_to_markdown(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """HTML descriptions are converted to markdown in output."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--status", "open"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # task-1 has HTML description — should be converted to markdown
        task1 = next(t for t in data if t["id"] == "task-1")
        assert "<ul>" not in task1["description"]
        assert "<li>" not in task1["description"]
        # Should contain markdown list items
        assert "check tests" in task1["description"]

    def test_plain_text_description_unchanged(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Plain text descriptions pass through without conversion."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--status", "open"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        task2 = next(t for t in data if t["id"] == "task-2")
        assert task2["description"] == "Plain text note, no formatting"
```

**Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_tasks.py::TestTaskDescriptionMarkdown -v`
Expected: FAIL (HTML not converted)

**Step 4: Write minimal implementation**

In `src/guten_morgen/output.py`, add import at top:

```python
from guten_morgen.markup import html_to_markdown
```

In `enrich_tasks()`, add after the `list_name` line (after line 224):

```python
        # description: convert HTML to markdown for agent-friendly output
        desc = t.get("description")
        if desc is not None:
            t["description"] = html_to_markdown(desc)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli_tasks.py::TestTaskDescriptionMarkdown -v`
Expected: PASS

**Step 6: Run full suite + mypy**

Run: `uv run pytest -x -q && uv run mypy src/`
Expected: All pass, clean

**Step 7: Commit**

```bash
git add src/guten_morgen/output.py tests/conftest.py tests/test_cli_tasks.py
git commit -m "feat(output): convert HTML descriptions to markdown in task enrichment"
```

---

### Task 6: Markdown conversion on write path

**Files:**
- Modify: `src/guten_morgen/cli.py:1137-1218`
- Modify: `tests/test_cli_tasks.py`

**Step 1: Write the failing tests**

In `tests/test_cli_tasks.py`, add:

```python
class TestTaskDescriptionMarkdownWrite:
    def test_create_converts_markdown_to_html(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Markdown description is converted to HTML when creating a task."""
        result = runner.invoke(cli, ["tasks", "create", "--title", "Test", "--description", "- item one\n- item two"])
        assert result.exit_code == 0

    def test_update_converts_markdown_to_html(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Markdown description is converted to HTML when updating a task."""
        result = runner.invoke(cli, ["tasks", "update", "task-1", "--description", "**bold note**"])
        assert result.exit_code == 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_tasks.py::TestTaskDescriptionMarkdownWrite -v`
Expected: These may pass already since we're not asserting HTML content (the mock accepts anything). But we still need to add the conversion to make real API calls work.

**Step 3: Write minimal implementation**

In `src/guten_morgen/cli.py`:

1. Add import near the top (where other imports are):

```python
from guten_morgen.markup import markdown_to_html
```

2. In `tasks_create`, change the description handling (around line 1162-1163) from:

```python
        if description:
            task_data["description"] = description
```

to:

```python
        if description:
            task_data["description"] = markdown_to_html(description) or description
```

3. Same change in `tasks_update` (around line 1206-1207).

**Step 4: Run full suite + mypy**

Run: `uv run pytest -x -q && uv run mypy src/`
Expected: All pass, clean

**Step 5: Commit**

```bash
git add src/guten_morgen/cli.py tests/test_cli_tasks.py
git commit -m "feat(cli): convert markdown descriptions to HTML on write"
```

---

### Task 7: Update usage docstring + tests

**Files:**
- Modify: `src/guten_morgen/cli.py` (usage function, around line 148)
- Modify: `tests/test_cli_usage.py`

**Step 1: Write the failing test**

In `tests/test_cli_usage.py`, add:

```python
    def test_contains_task_field_updates(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert result.exit_code == 0
        assert "--earliest-start" in result.output
        assert "0-9" in result.output
        assert "markdown" in result.output.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_usage.py::TestUsage::test_contains_task_field_updates -v`
Expected: FAIL

**Step 3: Update usage docstring**

In `src/guten_morgen/cli.py`, update the usage docstring:

1. On `gm tasks create` (around line 219), change `--priority 0-4` to `--priority 0-9` and add `[--earliest-start ISO]`:
```
- `gm tasks create --title TEXT [--due ISO] [--priority 0-9] [--description MARKDOWN]`
  `  [--duration MINUTES] [--tag NAME] [--list NAME] [--earliest-start ISO]`
  Create a new task. --duration sets estimatedDuration for AI time-blocking.
  --tag assigns tags by name (repeatable). --list assigns to a task list by name.
  --earliest-start sets the "not before" date. Descriptions accept markdown
  (converted to HTML for the API).
```

2. Same for `gm tasks update` — add `--earliest-start`, fix priority range, mention markdown.

3. Update the enrichment note (around line 213):
```
  Tasks are enriched with source, source_id, source_url, source_status,
  tag_names, list_name fields. Descriptions are converted from HTML to markdown.
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_usage.py::TestUsage::test_contains_task_field_updates -v`
Expected: PASS

**Step 5: Run full suite**

Run: `uv run pytest -x -q && uv run mypy src/`
Expected: All pass, clean

**Step 6: Commit**

```bash
git add src/guten_morgen/cli.py tests/test_cli_usage.py
git commit -m "docs: update usage with --earliest-start, priority 0-9, markdown descriptions"
```

---

### Task 8: Final verification

**Step 1: Full test suite with coverage**

Run: `uv run pytest -x -q --cov`
Expected: All pass, coverage >= 90%

**Step 2: Full mypy check**

Run: `uv run mypy src/`
Expected: clean

**Step 3: Pre-commit hooks**

Run: `uv run pre-commit run --all-files`
Expected: All pass

**Step 4: Clean up test tasks**

After verification, delete the test tasks from Morgen:
```bash
gm tasks list --json --status open | python3 -c "import sys,json; [print(t['id']) for t in json.load(sys.stdin) if 'Test for gm' in t.get('title','')]"
gm tasks delete <id1>
gm tasks delete <id2>
```
