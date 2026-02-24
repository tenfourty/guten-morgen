"""Tests for tasks commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient


class TestTasksList:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # 4 morgen-native + 1 linear + 1 notion = 6 total
        assert len(data) == 6
        assert data[0]["title"] == "Review PR"

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "list"])
        assert result.exit_code == 0
        assert "Review PR" in result.output

    def test_concise_format(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "list", "--json", "--response-format", "concise"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "id" in data[0]
        assert "priority" not in data[0]

    def test_limit(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "list", "--limit", "10", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) <= 10


class TestTasksListFiltering:
    """P1: Task filtering flags."""

    def test_status_open(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--status open filters to tasks with progress != completed."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--status", "open"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # task-4 has progress=completed, should be excluded
        ids = [t["id"] for t in data]
        assert "task-4" not in ids
        assert "task-1" in ids

    def test_status_completed(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--status completed filters to completed tasks only."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--status", "completed"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [t["id"] for t in data]
        assert "task-4" in ids
        assert "task-1" not in ids

    def test_status_all(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--status all returns everything."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--status", "all"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # 4 morgen-native + 1 linear + 1 notion = 6 total
        assert len(data) == 6

    def test_due_before(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--due-before filters tasks with due date before the given date."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--due-before", "2026-01-01"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [t["id"] for t in data]
        # task-3 (due 2025-10-15) should be included
        assert "task-3" in ids
        # task-1 (due 2026-02-17) should not
        assert "task-1" not in ids

    def test_due_after(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--due-after filters tasks with due date after the given date."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--due-after", "2026-01-01"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [t["id"] for t in data]
        assert "task-1" in ids
        assert "task-3" not in ids

    def test_overdue(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--overdue is shortcut for due-before now."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--overdue"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [t["id"] for t in data]
        # task-3 (due 2025-10-15) is overdue
        assert "task-3" in ids
        # task-4 (due 2026-02-16) is in the past too but completed
        assert "task-4" in ids

    def test_priority(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--priority filters by priority level."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--priority", "2"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [t["id"] for t in data]
        assert "task-1" in ids  # priority 2
        assert "task-2" not in ids  # priority 1

    def test_combined_filters(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Multiple filters combine with AND logic."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--status", "open", "--priority", "3"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [t["id"] for t in data]
        # task-3: open, priority 3 — should match
        assert "task-3" in ids
        assert len(ids) == 1


class TestTasksGet:
    def test_get(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "get", "task-1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "id" in data


class TestTasksCreate:
    def test_create(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "create", "--title", "New Task"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["title"] == "New Task"

    def test_create_with_options(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli,
            ["tasks", "create", "--title", "Urgent", "--priority", "4", "--due", "2026-02-18T12:00:00"],
        )
        assert result.exit_code == 0


class TestTasksUpdate:
    def test_update(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "update", "task-1", "--title", "Updated"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "task-1"
        assert data["title"] == "Updated"


class TestTasksClose:
    def test_close(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "close", "task-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "task-1"


class TestTasksReopen:
    def test_reopen(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "reopen", "task-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "task-1"


class TestTasksMove:
    def test_move(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "move", "task-2", "--after", "task-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "task-2"


class TestTasksDuration:
    def test_create_with_duration(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "create", "--title", "Quick task", "--duration", "30"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("estimatedDuration") == "PT30M"

    def test_update_with_duration(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "update", "task-1", "--duration", "45"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("estimatedDuration") == "PT45M"


class TestTasksSource:
    """Task 5: --source and --group-by-source flags."""

    def test_list_all_sources(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Default list returns tasks from all sources with enrichment."""
        result = runner.invoke(cli, ["tasks", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        sources = {t.get("source") for t in data}
        # Should have morgen-native, linear, and notion tasks
        assert "morgen" in sources
        assert "linear" in sources
        assert "notion" in sources

    def test_source_filter_morgen(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--source morgen returns only morgen-native tasks."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--source", "morgen"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        sources = {t.get("source") for t in data}
        assert sources == {"morgen"}
        # Should have the 4 morgen-native tasks
        assert len(data) == 4

    def test_source_filter_linear(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--source linear returns only linear tasks."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--source", "linear"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        sources = {t.get("source") for t in data}
        assert sources == {"linear"}
        assert data[0].get("source_id") == "ENG-1740"

    def test_enrichment_fields(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Enriched tasks have source, source_id, source_url, source_status."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--source", "linear"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        task = data[0]
        assert task["source"] == "linear"
        assert task["source_id"] == "ENG-1740"
        assert "linear.app" in task["source_url"]
        assert task["source_status"] == "In Progress"

    def test_group_by_source(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--group-by-source returns dict keyed by source."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--group-by-source"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert "morgen" in data
        assert "linear" in data
        assert "notion" in data
        assert isinstance(data["morgen"], list)

    def test_group_by_source_concise(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--group-by-source with --response-format concise applies field selection per group."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--group-by-source", "--response-format", "concise"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert "morgen" in data
        assert "linear" in data
        # Concise fields should be applied to tasks within each group
        for task in data["linear"]:
            assert "source" in task
            assert "title" in task


class TestGroupBySourceTableRendering:
    """Group-by-source with table format (non-JSON) renders section headers."""

    def test_group_by_source_table(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--group-by-source without --json renders table with section headers."""
        result = runner.invoke(cli, ["tasks", "list", "--group-by-source"])
        assert result.exit_code == 0
        # Section headers are rendered as "## <source>"
        assert "## morgen" in result.output
        assert "## linear" in result.output
        assert "## notion" in result.output
        # Task titles should appear in the table
        assert "Review PR" in result.output
        assert "Budget planning" in result.output

    def test_group_by_source_table_with_fields(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--group-by-source with --fields applies field selection per group."""
        result = runner.invoke(cli, ["tasks", "list", "--group-by-source", "--fields", "title,source"])
        assert result.exit_code == 0
        assert "## morgen" in result.output
        assert "Review PR" in result.output


class TestNormalizeDue:
    """Due date normalization for the Morgen API (exactly 19 chars)."""

    def test_date_only(self) -> None:
        from guten_morgen.cli import _normalize_due

        assert _normalize_due("2026-02-20") == "2026-02-20T23:59:59"

    def test_with_trailing_z(self) -> None:
        from guten_morgen.cli import _normalize_due

        assert _normalize_due("2026-02-20T23:59:59Z") == "2026-02-20T23:59:59"

    def test_already_correct(self) -> None:
        from guten_morgen.cli import _normalize_due

        assert _normalize_due("2026-02-20T23:59:59") == "2026-02-20T23:59:59"

    def test_with_timezone_offset(self) -> None:
        from guten_morgen.cli import _normalize_due

        assert _normalize_due("2026-02-20T23:59:59+01:00") == "2026-02-20T23:59:59"

    def test_partial_datetime(self) -> None:
        from guten_morgen.cli import _normalize_due

        # Only date+hour should still work (truncates to 19 chars)
        assert len(_normalize_due("2026-02-20T14:00")) <= 19

    def test_already_short(self) -> None:
        from guten_morgen.cli import _normalize_due

        assert _normalize_due("2026-02-20T14") == "2026-02-20T14"


class TestResolveTagNames:
    """Tag name resolution edge cases."""

    def test_unknown_tag_silently_skipped(self, mock_client: MorgenClient) -> None:
        """Tags that don't exist are silently filtered out."""
        from guten_morgen.cli import _resolve_tag_names

        result = _resolve_tag_names(mock_client, ("nonexistent",))
        assert result == []

    def test_mixed_known_and_unknown(self, mock_client: MorgenClient) -> None:
        """Known tags are resolved, unknown are skipped."""
        from guten_morgen.cli import _resolve_tag_names

        result = _resolve_tag_names(mock_client, ("urgent", "nonexistent"))
        assert result == ["tag-1"]


class TestTasksSchedule:
    """Task 10: tasks schedule CLI command."""

    def test_schedule_basic(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """tasks schedule creates a linked event from a task."""
        result = runner.invoke(
            cli,
            [
                "tasks",
                "schedule",
                "task-1",
                "--start",
                "2026-02-18T09:00:00",
                "--calendar-id",
                "cal-1",
                "--account-id",
                "acc-1",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["title"] == "Found item"
        meta = data.get("morgen.so:metadata", {})
        assert meta.get("taskId") == "task-1"

    def test_schedule_with_duration(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--duration overrides the task's estimatedDuration."""
        result = runner.invoke(
            cli,
            [
                "tasks",
                "schedule",
                "task-1",
                "--start",
                "2026-02-18T09:00:00",
                "--calendar-id",
                "cal-1",
                "--account-id",
                "acc-1",
                "--duration",
                "60",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["duration"] == "PT60M"

    def test_schedule_auto_discover(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Without --calendar-id/--account-id, auto-discovers from accounts."""
        result = runner.invoke(
            cli,
            ["tasks", "schedule", "task-1", "--start", "2026-02-18T09:00:00"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "calendarId" in data


class TestTasksTagFilter:
    """Tag filtering on tasks list."""

    def test_filter_by_tag_name(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--tag urgent returns only tasks tagged 'urgent'."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--tag", "urgent"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [t["id"] for t in data]
        assert "task-1" in ids  # tagged urgent
        assert "task-3" in ids  # tagged urgent + personal
        assert "task-2" not in ids  # tagged personal only
        assert "task-4" not in ids  # no tags

    def test_filter_by_tag_name_case_insensitive(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--tag matching is case-insensitive."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--tag", "URGENT"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [t["id"] for t in data]
        assert "task-1" in ids

    def test_filter_by_multiple_tags(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Multiple --tag flags combine with OR logic (match any)."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--tag", "urgent", "--tag", "personal"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [t["id"] for t in data]
        assert "task-1" in ids  # urgent
        assert "task-2" in ids  # personal
        assert "task-3" in ids  # both
        assert "task-4" not in ids  # no tags

    def test_tag_filter_combined_with_status(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--tag combines with other filters (AND logic)."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--tag", "urgent", "--status", "open"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        ids = [t["id"] for t in data]
        assert "task-1" in ids
        assert "task-3" in ids

    def test_tag_names_in_enriched_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Enriched tasks include tag_names field with resolved names."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--source", "morgen"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        task1 = next(t for t in data if t["id"] == "task-1")
        assert task1["tag_names"] == ["urgent"]
        task3 = next(t for t in data if t["id"] == "task-3")
        assert set(task3["tag_names"]) == {"urgent", "personal"}


class TestTasksCreateWithTag:
    """Tag assignment on task creation."""

    def test_create_with_tag(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--tag resolves name to ID and includes in create payload."""
        result = runner.invoke(cli, ["tasks", "create", "--title", "Tagged task", "--tag", "urgent"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "tag-1" in data.get("tags", [])

    def test_create_with_multiple_tags(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Multiple --tag flags add multiple tag IDs."""
        result = runner.invoke(cli, ["tasks", "create", "--title", "Multi-tag", "--tag", "urgent", "--tag", "personal"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "tag-1" in data.get("tags", [])
        assert "tag-2" in data.get("tags", [])


class TestTasksUpdateWithTag:
    """Tag assignment on task update."""

    def test_update_with_tag(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--tag on update sets tags on the task."""
        result = runner.invoke(cli, ["tasks", "update", "task-1", "--tag", "personal"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "tag-2" in data.get("tags", [])


class TestUpdatedAfter:
    def test_updated_after_option_accepted(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--updated-after is a valid option."""
        result = runner.invoke(cli, ["tasks", "list", "--json", "--updated-after", "2026-02-19T00:00:00"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


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


class TestTasksDelete:
    def test_delete(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "delete", "task-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "deleted"


class TestTasksCreateWithEarliestStart:
    def test_create_with_earliest_start_date(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "create", "--title", "New task", "--earliest-start", "2026-03-01"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("earliestStart") is not None

    def test_create_with_earliest_start_datetime(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["tasks", "create", "--title", "New task", "--earliest-start", "2026-03-01T09:00:00"]
        )
        assert result.exit_code == 0


class TestTasksUpdateWithEarliestStart:
    def test_update_with_earliest_start(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "update", "task-1", "--earliest-start", "2026-03-15"])
        assert result.exit_code == 0
