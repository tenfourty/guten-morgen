"""Tests for calendars commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient


class TestCalendarsList:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["calendars", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 3

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["calendars", "list"])
        assert result.exit_code == 0
        assert "Work" in result.output


class TestCalendarsUpdate:
    def test_update_name(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["calendars", "update", "cal-1", "--account-id", "acc-1", "--name", "New Name"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "id" in data or "status" in data

    def test_update_color(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["calendars", "update", "cal-1", "--account-id", "acc-1", "--color", "#ff0000"])
        assert result.exit_code == 0

    def test_update_busy(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["calendars", "update", "cal-1", "--account-id", "acc-1", "--busy"])
        assert result.exit_code == 0

    def test_update_auto_discover_account(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Without --account-id, auto-discovers from accounts."""
        result = runner.invoke(cli, ["calendars", "update", "cal-1", "--name", "X"])
        assert result.exit_code == 0
