"""Tests for tasks commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from morgen.cli import cli
from morgen.client import MorgenClient


class TestTasksList:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 4
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
        assert len(data) == 4

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
        assert "id" in data


class TestTasksClose:
    def test_close(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "close", "task-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "id" in data


class TestTasksReopen:
    def test_reopen(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "reopen", "task-1"])
        assert result.exit_code == 0


class TestTasksMove:
    def test_move(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "move", "task-2", "--after", "task-1"])
        assert result.exit_code == 0


class TestTasksDelete:
    def test_delete(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tasks", "delete", "task-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "deleted"
