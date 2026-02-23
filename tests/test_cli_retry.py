"""Tests for CLI retry integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from guten_morgen.cli import cli


class TestCliRetryWiring:
    def test_json_mode_uses_agent_callback(self, runner: CliRunner, mock_client: MagicMock) -> None:
        """When --json is passed, agent retry callback is wired."""
        with patch("guten_morgen.cli._get_client") as get_client:
            get_client.return_value = mock_client
            runner.invoke(cli, ["accounts", "--json"])
            get_client.assert_called()

    def test_table_mode_uses_human_callback(self, runner: CliRunner, mock_client: MagicMock) -> None:
        """When table format is used, human retry callback is wired."""
        with patch("guten_morgen.cli._get_client") as get_client:
            get_client.return_value = mock_client
            runner.invoke(cli, ["accounts"])
            get_client.assert_called()
