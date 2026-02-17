"""Tests for the `morgen next` command."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

from click.testing import CliRunner

from morgen.cli import cli
from morgen.client import MorgenClient


class TestNext:
    def test_default_returns_events(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Default invocation returns next events as JSON."""
        result = runner.invoke(cli, ["next", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_count_flag(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--count limits number of events returned."""
        result = runner.invoke(cli, ["next", "--json", "--count", "1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) <= 1

    def test_filters_past_events(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Only events starting after now are included."""
        # Freeze time to before the first fake event (09:00)
        frozen = datetime(2026, 2, 17, 8, 0, 0, tzinfo=timezone.utc)
        with patch("morgen.cli._now_utc", return_value=frozen):
            result = runner.invoke(cli, ["next", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Both fake events (09:00 and 12:00) are after 08:00
        assert len(data) == 2

    def test_filters_past_events_mid_day(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Events that have already started are excluded."""
        # Freeze time to after standup (09:00) but before lunch (12:00)
        frozen = datetime(2026, 2, 17, 10, 0, 0, tzinfo=timezone.utc)
        with patch("morgen.cli._now_utc", return_value=frozen):
            result = runner.invoke(cli, ["next", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Only Lunch (12:00) should remain
        assert len(data) == 1
        assert data[0]["title"] == "Lunch"

    def test_concise_format(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Concise format excludes calendarId."""
        result = runner.invoke(cli, ["next", "--json", "--response-format", "concise"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        if data:
            assert "calendarId" not in data[0]

    def test_looks_ahead_24h(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Query window is from now to 24h ahead by default."""
        # Freeze time to well after all fake events — should get nothing
        frozen = datetime(2026, 2, 17, 23, 0, 0, tzinfo=timezone.utc)
        with patch("morgen.cli._now_utc", return_value=frozen):
            result = runner.invoke(cli, ["next", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # No events after 23:00 today in fake data
        assert len(data) == 0

    def test_hours_flag(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--hours extends the look-ahead window."""
        result = runner.invoke(cli, ["next", "--json", "--hours", "48"])
        assert result.exit_code == 0
