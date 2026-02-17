"""Tests for quick view commands (today, this-week, this-month)."""

from __future__ import annotations

import json

from click.testing import CliRunner

from morgen.cli import cli
from morgen.client import MorgenClient


class TestToday:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["today", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        # Should have events tagged with type
        types = {item["type"] for item in data}
        assert "event" in types

    def test_concise_format(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["today", "--json", "--response-format", "concise"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) > 0
        assert "type" in data[0]
        # Concise should not include calendarId
        events = [d for d in data if d["type"] == "event"]
        if events:
            assert "calendarId" not in events[0]

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["today"])
        assert result.exit_code == 0
        assert "Standup" in result.output


class TestThisWeek:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["this-week", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


class TestThisMonth:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["this-month", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


class TestCombinedViewSorting:
    def test_events_sorted_by_start(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["today", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        events = [d for d in data if d["type"] == "event"]
        if len(events) >= 2:
            assert events[0]["start"] <= events[1]["start"]
