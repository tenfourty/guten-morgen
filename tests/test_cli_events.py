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
        assert len(data) == 3
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

    def test_concise_excludes_attendees_and_location(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Concise format does not include attendees or location (API doesn't return them)."""
        from morgen.cli import EVENT_CONCISE_FIELDS

        assert "attendees" not in EVENT_CONCISE_FIELDS
        assert "location" not in EVENT_CONCISE_FIELDS


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
        assert len(data) == 2
        titles = [e["title"] for e in data]
        assert "Standup" in titles
        assert "Lunch" in titles
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
        # Fake IDs are short (evt-1) so they stay as-is; test the flag works
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
        assert "id" in data


class TestEventsDelete:
    def test_delete(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "delete", "evt-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "deleted"
