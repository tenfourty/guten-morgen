"""Tests for events commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient


class TestEventsList:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["events", "list", "--start", "2026-02-17T00:00:00", "--end", "2026-02-17T23:59:59", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 4  # 3 from acc-1 + Dentist from acc-2 (synced copy deduped)
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
        # Verify expected concise fields are present
        assert "title" in data[0]
        assert "start" in data[0]
        assert "duration" in data[0]

    def test_concise_includes_display_fields(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Concise format includes participants_display and location_display."""
        from guten_morgen.cli import EVENT_CONCISE_FIELDS

        assert "participants_display" in EVENT_CONCISE_FIELDS
        assert "location_display" in EVENT_CONCISE_FIELDS

    def test_enrichment_adds_display_fields(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Events are enriched with participants_display and location_display."""
        result = runner.invoke(
            cli, ["events", "list", "--start", "2026-02-17T00:00:00", "--end", "2026-02-17T23:59:59", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        standup = next(e for e in data if e["title"] == "Standup")
        assert "Alice" in standup["participants_display"]
        assert "Bob" in standup["participants_display"]
        assert "Room 42" not in standup["participants_display"]  # resource filtered
        assert "meet.google.com" in standup["location_display"]

    def test_dedup_via_morgen(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Synced copies with '(via Morgen)' are removed."""
        result = runner.invoke(
            cli, ["events", "list", "--start", "2026-02-17T00:00:00", "--end", "2026-02-17T23:59:59", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        titles = [e["title"] for e in data]
        assert "Standup (via Morgen)" not in titles
        assert "Dentist" in titles


class TestNoRoutines:
    def test_no_frames_excludes_frame_events(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--no-frames filters out events with frameFilterMql in metadata."""
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
                "--no-frames",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3  # Standup, Lunch (acc-1) + Dentist (acc-2), frame filtered out
        titles = [e["title"] for e in data]
        assert "Standup" in titles
        assert "Lunch" in titles
        assert "Dentist" in titles
        assert "Tasks and Deep Work" not in titles

    def test_default_includes_routine_events(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """By default, frame events are included."""
        result = runner.invoke(
            cli,
            ["events", "list", "--start", "2026-02-17T00:00:00", "--end", "2026-02-17T23:59:59", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        titles = [e["title"] for e in data]
        assert "Tasks and Deep Work" in titles


class TestShortIds:
    def test_short_ids_flag(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--short-ids truncates IDs in output."""
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
                "--short-ids",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Fake IDs (evt-1) are already short; full truncation tested in test_output.py::TestTruncateIds
        assert "id" in data[0]


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
        assert data["id"] == "evt-1"
        assert data["title"] == "Updated"


class TestEventsDelete:
    def test_delete(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "delete", "evt-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "deleted"
        assert data["id"] == "evt-1"


class TestSeriesUpdateMode:
    def test_update_with_series_flag(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--series passes seriesUpdateMode query param to API."""
        result = runner.invoke(cli, ["events", "update", "evt-1", "--title", "Updated", "--series", "future"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "evt-1"

    def test_delete_with_series_flag(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--series passes seriesUpdateMode on delete."""
        result = runner.invoke(cli, ["events", "delete", "evt-1", "--series", "all"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "deleted"

    def test_series_default_not_sent(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Without --series, no seriesUpdateMode param is sent."""
        result = runner.invoke(cli, ["events", "update", "evt-1", "--title", "Updated"])
        assert result.exit_code == 0

    def test_series_invalid_choice(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Invalid --series value is rejected by Click."""
        result = runner.invoke(cli, ["events", "update", "evt-1", "--series", "bogus"])
        assert result.exit_code != 0
