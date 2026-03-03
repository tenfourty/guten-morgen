"""Tests for the --help output (replaces usage command)."""

from __future__ import annotations

from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient


class TestHelpContainsLLMContract:
    """The --help output includes the LLM API contract content (formerly in usage)."""

    def test_contains_command_signatures(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
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
        result = runner.invoke(cli, ["--help"])
        assert "--format" in result.output
        assert "--json" in result.output
        assert "--fields" in result.output
        assert "--jq" in result.output
        assert "--response-format" in result.output
        assert "--no-cache" in result.output

    def test_contains_cache_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "gm cache clear" in result.output
        assert "gm cache stats" in result.output

    def test_contains_workflow(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert "Recommended Agent Workflow" in result.output

    def test_contains_new_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert "gm next" in result.output
        assert "--events-only" in result.output
        assert "--tasks-only" in result.output
        assert "--short-ids" in result.output
        assert "--status" in result.output
        assert "--overdue" in result.output
        assert "--no-frames" in result.output

    def test_contains_group_options(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert "--group" in result.output
        assert "--all-calendars" in result.output
        assert "gm groups" in result.output
        assert "Calendar Groups" in result.output

    def test_contains_multi_source_features(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "--source" in result.output
        assert "--group-by-source" in result.output
        assert "--duration" in result.output
        assert "gm tasks schedule" in result.output
        assert "Morning Triage" in result.output or "Scenario" in result.output

    def test_contains_lists_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "gm lists list" in result.output
        assert "gm lists create" in result.output
        assert "gm lists update" in result.output
        assert "gm lists delete" in result.output
        assert "--list" in result.output

    def test_contains_task_field_updates(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "--earliest-start" in result.output
        assert "0-9" in result.output
        assert "markdown" in result.output.lower()


class TestHelpInitStatus:
    """The --help output includes initialization status frontmatter."""

    def test_shows_config_status(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Config" in result.output

    def test_shows_connected_task_sources(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Connected Task Sources" in result.output
        assert "linear" in result.output
        assert "notion" in result.output


class TestBareGmShowsHelp:
    """Bare `gm` (no args) shows the same output as --help."""

    def test_bare_invocation(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        assert "gm accounts" in result.output
        assert "Recommended Agent Workflow" in result.output


class TestUsageCommandRemoved:
    """The old `usage` command is gone."""

    def test_usage_command_not_found(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert result.exit_code != 0
