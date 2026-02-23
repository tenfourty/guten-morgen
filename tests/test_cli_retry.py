"""Tests for CLI retry integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from guten_morgen.cli import cli


class TestCliRetryWiring:
    def test_json_mode_passes_json_fmt(self, runner: CliRunner, mock_client: MagicMock) -> None:
        """When --json is passed, _get_client receives fmt='json'."""
        with patch("guten_morgen.cli._get_client") as get_client:
            get_client.return_value = mock_client
            runner.invoke(cli, ["accounts", "--json"])
            get_client.assert_called_once_with("json")

    def test_table_mode_passes_table_fmt(self, runner: CliRunner, mock_client: MagicMock) -> None:
        """When table format is used, _get_client receives fmt='table'."""
        with patch("guten_morgen.cli._get_client") as get_client:
            get_client.return_value = mock_client
            runner.invoke(cli, ["accounts"])
            get_client.assert_called_once_with("table")
