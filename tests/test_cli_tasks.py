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
        assert len(data) == 2
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
