"""Tests for the usage command."""

from __future__ import annotations

from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient


class TestUsage:
    def test_contains_command_signatures(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert result.exit_code == 0
        assert "gm accounts" in result.output
        assert "gm events list" in result.output
        assert "gm tasks list" in result.output
        assert "gm tasks create" in result.output
        assert "gm tags list" in result.output
        assert "gm today" in result.output
        assert "gm this-week" in result.output
        assert "gm this-month" in result.output

    def test_contains_global_options(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert "--format" in result.output
        assert "--json" in result.output
        assert "--fields" in result.output
        assert "--jq" in result.output
        assert "--response-format" in result.output
        assert "--no-cache" in result.output

    def test_contains_cache_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert result.exit_code == 0
        assert "gm cache clear" in result.output
        assert "gm cache stats" in result.output

    def test_contains_workflow(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert "Recommended Agent Workflow" in result.output

    def test_contains_new_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert "gm next" in result.output
        assert "--events-only" in result.output
        assert "--tasks-only" in result.output
        assert "--short-ids" in result.output
        assert "--status" in result.output
        assert "--overdue" in result.output
        assert "--no-frames" in result.output

    def test_contains_group_options(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert "--group" in result.output
        assert "--all-calendars" in result.output
        assert "gm groups" in result.output
        assert "Calendar Groups" in result.output

    def test_contains_multi_source_features(self, runner: CliRunner) -> None:
        """Task 11: usage includes multi-source task features."""
        result = runner.invoke(cli, ["usage"])
        assert result.exit_code == 0
        # --source and --group-by-source on tasks list
        assert "--source" in result.output
        assert "--group-by-source" in result.output
        # --duration on tasks create/update
        assert "--duration" in result.output
        # tasks schedule command
        assert "gm tasks schedule" in result.output
        # Scenarios section
        assert "Morning Triage" in result.output or "Scenario" in result.output

    def test_contains_lists_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert result.exit_code == 0
        assert "gm lists list" in result.output
        assert "gm lists create" in result.output
        assert "gm lists update" in result.output
        assert "gm lists delete" in result.output
        assert "--list" in result.output

    def test_contains_task_field_updates(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert result.exit_code == 0
        assert "--earliest-start" in result.output
        assert "0-9" in result.output
        assert "markdown" in result.output.lower()

    def test_shows_connected_task_sources(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """usage dynamically discovers and shows connected task sources."""
        result = runner.invoke(cli, ["usage"])
        assert result.exit_code == 0
        assert "Connected Task Sources" in result.output
        assert "linear" in result.output
        assert "notion" in result.output
