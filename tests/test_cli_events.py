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
        assert len(data) == 5  # 4 from acc-1 (incl. declined) + Dentist from acc-2 (synced copy deduped)
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
        assert len(data) == 4  # Standup, Lunch, Optional Open Hours (acc-1) + Dentist (acc-2), frame filtered out
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


class TestBareDateNormalization:
    def test_bare_date_accepted(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Bare dates (YYYY-MM-DD) are normalized to full ISO datetimes."""
        result = runner.invoke(cli, ["events", "list", "--start", "2026-02-17", "--end", "2026-02-17", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1

    def test_full_datetime_unchanged(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Full ISO datetimes pass through unchanged."""
        result = runner.invoke(
            cli, ["events", "list", "--start", "2026-02-17T00:00:00", "--end", "2026-02-17T23:59:59", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 5


class TestEventsCreate:
    def test_create(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["events", "create", "--title", "Test Event", "--start", "2026-02-17T10:00:00", "--duration", "30"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["title"] == "Test Event"

    def test_create_with_privacy(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--privacy sets the privacy field on created events."""
        result = runner.invoke(
            cli,
            [
                "events",
                "create",
                "--title",
                "Private Meeting",
                "--start",
                "2026-02-17T10:00:00",
                "--duration",
                "30",
                "--privacy",
                "private",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["privacy"] == "private"

    def test_create_without_privacy(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Without --privacy, no privacy field in payload."""
        result = runner.invoke(
            cli,
            ["events", "create", "--title", "Open Meeting", "--start", "2026-02-17T10:00:00", "--duration", "30"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("privacy") is None

    def test_create_privacy_invalid_choice(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Invalid --privacy value is rejected by Click."""
        result = runner.invoke(
            cli,
            [
                "events",
                "create",
                "--title",
                "Bad",
                "--start",
                "2026-02-17T10:00:00",
                "--duration",
                "30",
                "--privacy",
                "confidential",
            ],
        )
        assert result.exit_code != 0


class TestEventsUpdate:
    def test_update(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "update", "evt-1", "--title", "Updated"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "evt-1"
        assert data["title"] == "Updated"

    def test_update_privacy(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--privacy updates the visibility of an event."""
        result = runner.invoke(cli, ["events", "update", "evt-1", "--privacy", "secret"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "evt-1"
        assert data["privacy"] == "secret"

    def test_update_privacy_to_public(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Can set privacy back to public."""
        result = runner.invoke(cli, ["events", "update", "evt-1", "--privacy", "public"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["privacy"] == "public"


class TestEventsDelete:
    def test_delete(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "delete", "evt-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "deleted"
        assert data["id"] == "evt-1"


class TestGoogleMeet:
    def test_create_with_meet(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--meet adds morgen.so:requestVirtualRoom to the payload."""
        result = runner.invoke(
            cli, ["events", "create", "--title", "Sync", "--start", "2026-02-18T10:00:00", "--duration", "30", "--meet"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("morgen.so:requestVirtualRoom") == "default"

    def test_create_without_meet(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """Without --meet, no requestVirtualRoom field."""
        result = runner.invoke(
            cli, ["events", "create", "--title", "Sync", "--start", "2026-02-18T10:00:00", "--duration", "30"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "morgen.so:requestVirtualRoom" not in data


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


class TestHideDeclined:
    def test_hide_declined_excludes_declined_events(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--hide-declined filters out events where account owner declined."""
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
                "--hide-declined",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        titles = [e["title"] for e in data]
        assert "Optional Open Hours" not in titles
        assert "Standup" in titles

    def test_default_includes_declined_events(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """By default, declined events are included."""
        result = runner.invoke(
            cli,
            ["events", "list", "--start", "2026-02-17T00:00:00", "--end", "2026-02-17T23:59:59", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        titles = [e["title"] for e in data]
        assert "Optional Open Hours" in titles

    def test_my_status_in_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """my_status field appears in JSON output."""
        result = runner.invoke(
            cli,
            ["events", "list", "--start", "2026-02-17T00:00:00", "--end", "2026-02-17T23:59:59", "--json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        standup = next(e for e in data if e["title"] == "Standup")
        declined = next(e for e in data if e["title"] == "Optional Open Hours")
        assert standup["my_status"] == "accepted"
        assert declined["my_status"] == "declined"

    def test_my_status_in_concise_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """my_status field is included in concise format."""
        from guten_morgen.cli import EVENT_CONCISE_FIELDS

        assert "my_status" in EVENT_CONCISE_FIELDS


class TestEventsRsvp:
    def test_accept(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "rsvp", "evt-1", "--action", "accept"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "eventId" in data or "status" in data

    def test_decline(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "rsvp", "evt-1", "--action", "decline"])
        assert result.exit_code == 0

    def test_tentative(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "rsvp", "evt-1", "--action", "tentative"])
        assert result.exit_code == 0

    def test_with_comment(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "rsvp", "evt-1", "--action", "accept", "--comment", "Will be 5min late"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("comment") == "Will be 5min late"

    def test_no_notify(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "rsvp", "evt-1", "--action", "decline", "--no-notify"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data.get("notifyOrganizer") is False

    def test_action_required(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "rsvp", "evt-1"])
        assert result.exit_code != 0

    def test_invalid_action(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "rsvp", "evt-1", "--action", "maybe"])
        assert result.exit_code != 0

    def test_with_series_mode(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["events", "rsvp", "evt-1", "--action", "accept", "--series", "all"])
        assert result.exit_code == 0


class TestEventStatusFilter:
    def test_include_accepted_only(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--event-status accepted returns only accepted events."""
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
                "--event-status",
                "accepted",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        statuses = {e.get("my_status") or "null" for e in data}
        assert statuses == {"accepted"}

    def test_include_null_status(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--event-status null returns events with no participants (my_status is None)."""
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
                "--event-status",
                "null",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Lunch, Tasks and Deep Work, Dentist have no accountOwner → my_status=null
        assert all(e.get("my_status") is None for e in data)
        assert len(data) >= 1

    def test_include_multiple_statuses(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--event-status accepted,null returns both."""
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
                "--event-status",
                "accepted,null",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        statuses = {e.get("my_status") or "null" for e in data}
        assert "declined" not in statuses

    def test_hide_declined_still_works(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--hide-declined continues to work as a convenience alias."""
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
                "--hide-declined",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        titles = [e["title"] for e in data]
        assert "Optional Open Hours" not in titles

    def test_event_status_overrides_hide_declined(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--event-status takes priority over --hide-declined."""
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
                "--event-status",
                "declined",
                "--hide-declined",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        # --event-status takes priority, so declined events are included
        statuses = {e.get("my_status") or "null" for e in data}
        assert statuses == {"declined"}


class TestCounts:
    def test_counts_wraps_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--counts wraps JSON output with events and meta."""
        result = runner.invoke(
            cli,
            ["events", "list", "--start", "2026-02-17T00:00:00", "--end", "2026-02-17T23:59:59", "--json", "--counts"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "events" in data
        assert "meta" in data
        assert "status_counts" in data["meta"]
        assert "total" in data["meta"]
        assert data["meta"]["total"] == len(data["events"])

    def test_counts_status_distribution(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--counts includes correct status distribution."""
        result = runner.invoke(
            cli,
            ["events", "list", "--start", "2026-02-17T00:00:00", "--end", "2026-02-17T23:59:59", "--json", "--counts"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        counts = data["meta"]["status_counts"]
        assert counts.get("accepted", 0) >= 1  # Standup
        assert counts.get("declined", 0) >= 1  # Optional Open Hours
        assert counts.get("null", 0) >= 1  # Lunch, etc.

    def test_counts_without_json_ignored(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--counts without --json outputs normal table (not wrapped)."""
        result = runner.invoke(
            cli,
            ["events", "list", "--start", "2026-02-17T00:00:00", "--end", "2026-02-17T23:59:59", "--counts"],
        )
        assert result.exit_code == 0
        # Table output — should not be JSON-parseable
        assert "Standup" in result.output

    def test_counts_with_event_status_filter(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--counts respects --event-status filter in both events and counts."""
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
                "--counts",
                "--event-status",
                "accepted,null",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        counts = data["meta"]["status_counts"]
        assert "declined" not in counts

    def test_counts_jsonl_not_wrapped(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--counts with --format jsonl should NOT wrap output — JSONL is line-per-record."""
        result = runner.invoke(
            cli,
            [
                "events",
                "list",
                "--start",
                "2026-02-17T00:00:00",
                "--end",
                "2026-02-17T23:59:59",
                "--format",
                "jsonl",
                "--counts",
            ],
        )
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        # Each line should be a standalone event object, not a wrapper
        for line in lines:
            record = json.loads(line)
            assert "meta" not in record
            assert "title" in record


class TestEventPrivacyModel:
    def test_model_accepts_privacy(self) -> None:
        """Event model parses privacy field from API response."""
        from guten_morgen.models import Event

        event = Event(id="evt-1", title="Private", privacy="private")
        assert event.privacy == "private"

    def test_model_accepts_free_busy_status(self) -> None:
        """Event model parses freeBusyStatus field from API response."""
        from guten_morgen.models import Event

        event = Event(id="evt-1", title="Busy", freeBusyStatus="busy")
        assert event.freeBusyStatus == "busy"

    def test_privacy_in_model_dump(self) -> None:
        """Privacy field appears in model_dump output."""
        from guten_morgen.models import Event

        event = Event(id="evt-1", title="Secret", privacy="secret")
        dumped = event.model_dump(exclude_none=True)
        assert dumped["privacy"] == "secret"

    def test_privacy_none_excluded(self) -> None:
        """Privacy field excluded from model_dump when None."""
        from guten_morgen.models import Event

        event = Event(id="evt-1", title="Normal")
        dumped = event.model_dump(exclude_none=True)
        assert "privacy" not in dumped


class TestNormalizeDatetime:
    def test_bare_date(self) -> None:
        from guten_morgen.cli import _normalize_datetime

        assert _normalize_datetime("2026-03-03") == "2026-03-03T00:00:00"

    def test_full_datetime_unchanged(self) -> None:
        from guten_morgen.cli import _normalize_datetime

        assert _normalize_datetime("2026-03-03T10:30:00") == "2026-03-03T10:30:00"

    def test_datetime_with_timezone(self) -> None:
        from guten_morgen.cli import _normalize_datetime

        assert _normalize_datetime("2026-03-03T10:30:00+01:00") == "2026-03-03T10:30:00+01:00"
