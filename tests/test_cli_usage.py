"""Tests for the usage command."""

from __future__ import annotations

from click.testing import CliRunner

from morgen.cli import cli
from morgen.client import MorgenClient


class TestUsage:
    def test_contains_command_signatures(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert result.exit_code == 0
        assert "morgen accounts" in result.output
        assert "morgen events list" in result.output
        assert "morgen tasks list" in result.output
        assert "morgen tasks create" in result.output
        assert "morgen tags list" in result.output
        assert "morgen today" in result.output
        assert "morgen this-week" in result.output
        assert "morgen this-month" in result.output

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
        assert "morgen cache clear" in result.output
        assert "morgen cache stats" in result.output

    def test_contains_workflow(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert "Recommended Agent Workflow" in result.output

    def test_contains_new_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert "morgen next" in result.output
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
        assert "morgen groups" in result.output
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
        assert "morgen tasks schedule" in result.output
        # Scenarios section
        assert "Morning Triage" in result.output or "Scenario" in result.output

    def test_shows_connected_task_sources(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """usage dynamically discovers and shows connected task sources."""
        result = runner.invoke(cli, ["usage"])
        assert result.exit_code == 0
        assert "Connected Task Sources" in result.output
        assert "linear" in result.output
        assert "notion" in result.output
