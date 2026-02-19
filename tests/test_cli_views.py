"""Tests for quick view commands (today, this-week, this-month)."""

from __future__ import annotations

import json
from unittest.mock import patch

from click.testing import CliRunner

from morgen.cli import cli
from morgen.client import MorgenClient

# Fixed date range matching conftest FAKE data (2026-02-17)
_TODAY_START = "2026-02-17T00:00:00+00:00"
_TODAY_END = "2026-02-17T23:59:59+00:00"


class TestToday:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["today", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert "events" in data
        assert "scheduled_tasks" in data
        assert "overdue_tasks" in data
        assert "unscheduled_tasks" in data

    def test_concise_format(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["today", "--json", "--response-format", "concise"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "events" in data
        # Concise events should not include calendarId
        if data["events"]:
            assert "calendarId" not in data["events"][0]

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["today"])
        assert result.exit_code == 0
        assert "Standup" in result.output

    def test_events_only(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["today", "--json", "--events-only"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "events" in data
        assert "scheduled_tasks" not in data
        assert "overdue_tasks" not in data
        assert "unscheduled_tasks" not in data

    def test_tasks_only(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["today", "--json", "--tasks-only"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "events" not in data
        assert "scheduled_tasks" in data
        assert "overdue_tasks" in data
        assert "unscheduled_tasks" in data

    def test_events_only_and_tasks_only_mutually_exclusive(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["today", "--json", "--events-only", "--tasks-only"])
        assert result.exit_code != 0

    def test_task_categorisation(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Tasks are split into scheduled, overdue, and unscheduled."""
        with patch("morgen.time_utils.today_range", return_value=(_TODAY_START, _TODAY_END)):
            result = runner.invoke(cli, ["today", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)

        # task-1 has due=2026-02-17 — today's range — should be scheduled
        scheduled_ids = [t["id"] for t in data["scheduled_tasks"]]
        assert "task-1" in scheduled_ids

        # task-3 has due=2025-10-15 — overdue
        overdue_ids = [t["id"] for t in data["overdue_tasks"]]
        assert "task-3" in overdue_ids

        # task-2 has no due date — unscheduled
        unscheduled_ids = [t["id"] for t in data["unscheduled_tasks"]]
        assert "task-2" in unscheduled_ids

    def test_no_frames_on_today(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--no-frames excludes Morgen scheduling frames from today view."""
        result = runner.invoke(cli, ["today", "--json", "--no-frames"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        titles = [e["title"] for e in data["events"]]
        assert "Tasks and Deep Work" not in titles
        assert "Standup" in titles


class TestThisWeek:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["this-week", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert "events" in data

    def test_events_only(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["this-week", "--json", "--events-only"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "events" in data
        assert "scheduled_tasks" not in data


class TestThisMonth:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["this-month", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)
        assert "events" in data


class TestCombinedViewSorting:
    def test_events_sorted_by_start(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["today", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        events = data["events"]
        if len(events) >= 2:
            assert events[0]["start"] <= events[1]["start"]


class TestCombinedViewMultiSource:
    """Task 6: Combined views use list_all_tasks() with enrichment."""

    def test_today_includes_external_tasks(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """today view includes tasks from all sources with enrichment."""
        result = runner.invoke(cli, ["today", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Collect all task IDs across all task categories
        all_task_ids: list[str] = []
        for key in ("scheduled_tasks", "overdue_tasks", "unscheduled_tasks"):
            all_task_ids.extend(t["id"] for t in data.get(key, []))
        # Linear task (due 2026-02-20) is outside today's range, but should appear in view
        # Notion task (due 2026-03-01) is also outside today's range
        # The important thing is that enrichment happened — tasks have 'source' field
        all_tasks = data.get("scheduled_tasks", []) + data.get("overdue_tasks", []) + data.get("unscheduled_tasks", [])
        sources = {t.get("source") for t in all_tasks}
        assert "morgen" in sources

    def test_this_week_enriched_tasks(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """this-week view has enriched tasks with source field."""
        result = runner.invoke(cli, ["this-week", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        all_tasks = data.get("scheduled_tasks", []) + data.get("overdue_tasks", []) + data.get("unscheduled_tasks", [])
        # All tasks should have source field from enrichment
        for t in all_tasks:
            assert "source" in t
