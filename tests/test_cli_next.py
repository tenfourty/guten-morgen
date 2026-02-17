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
        # All fake events (09:00, 12:00, 14:00 on acc-1 + 16:00 on acc-2) are after 08:00
        assert len(data) == 4

    def test_filters_past_events_mid_day(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Events that have already started are excluded."""
        # Freeze time to after standup (09:00) but before lunch (12:00)
        frozen = datetime(2026, 2, 17, 10, 0, 0, tzinfo=timezone.utc)
        with patch("morgen.cli._now_utc", return_value=frozen):
            result = runner.invoke(cli, ["next", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Lunch (12:00), Deep Work (14:00), Dentist (16:00) remain
        assert len(data) == 3
        assert data[0]["title"] == "Lunch"

    def test_concise_format(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Concise format excludes calendarId."""
        result = runner.invoke(cli, ["next", "--json", "--response-format", "concise"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        if data:
            assert "calendarId" not in data[0]

    def test_window_covers_through_end_of_next_day(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Query window extends from now through end of tomorrow (23:59:59 UTC)."""
        # At 23:00 on Feb 17, window should cover until end of Feb 18
        # Fake events on Feb 17 at 09:00/12:00/14:00/16:00 are all in the past
        frozen = datetime(2026, 2, 17, 23, 0, 0, tzinfo=timezone.utc)
        with patch("morgen.cli._now_utc", return_value=frozen):
            result = runner.invoke(cli, ["next", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # All fake events are before 23:00, so none are upcoming
        assert len(data) == 0

    def test_no_frames_on_next(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--no-frames excludes Morgen scheduling frames from next."""
        frozen = datetime(2026, 2, 17, 8, 0, 0, tzinfo=timezone.utc)
        with patch("morgen.cli._now_utc", return_value=frozen):
            result = runner.invoke(cli, ["next", "--json", "--no-frames", "--count", "10"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        titles = [e["title"] for e in data]
        assert "Tasks and Deep Work" not in titles
        assert "Standup" in titles
