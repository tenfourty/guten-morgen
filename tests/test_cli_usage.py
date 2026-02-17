"""Tests for the usage command."""

from __future__ import annotations

from click.testing import CliRunner

from morgen.cli import cli


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

    def test_contains_workflow(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["usage"])
        assert "Recommended Workflow" in result.output
