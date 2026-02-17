"""Tests for accounts and calendars commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from morgen.cli import cli
from morgen.client import MorgenClient


class TestAccounts:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["accounts", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["accountId"] == "acc-1"

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["accounts"])
        assert result.exit_code == 0
        assert "Work Google" in result.output

    def test_concise_format(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["accounts", "--json", "--response-format", "concise"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "accountId" in data[0]
        assert "name" in data[0]
        assert "email" not in data[0]

    def test_fields_filter(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["accounts", "--json", "--fields", "name"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "name" in data[0]
        assert "accountId" not in data[0]


class TestCalendars:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["calendars", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["name"] == "Work"

    def test_concise_format(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["calendars", "--json", "--response-format", "concise"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "calendarId" in data[0]
        assert "accountId" not in data[0]
