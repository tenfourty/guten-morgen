"""Tests for events commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from morgen.cli import cli
from morgen.client import MorgenClient


class TestEventsList:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["events", "list", "--start", "2026-02-17T00:00:00", "--end", "2026-02-17T23:59:59", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["title"] == "Standup"

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["events", "list", "--start", "2026-02-17T00:00:00", "--end", "2026-02-17T23:59:59"]
        )
        assert result.exit_code == 0
        assert "Standup" in result.output

    def test_concise_format(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli,
            [
                "events",
                "list",
                "--start",
                "2026-02-17T00:00:00",
                "--end",
                "2026-02-17T23:59:59",
                "--json",
                "--response-format",
                "concise",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "id" in data[0]
        assert "calendarId" not in data[0]


class TestEventsCreate:
    def test_create(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["events", "create", "--title", "Test Event", "--start", "2026-02-17T10:00:00", "--duration", "30"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["title"] == "Test Event"


class TestEventsUpdate:
    def test_update(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "update", "evt-1", "--title", "Updated"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "id" in data


class TestEventsDelete:
    def test_delete(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "delete", "evt-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "deleted"
