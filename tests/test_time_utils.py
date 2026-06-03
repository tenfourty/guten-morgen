"""Tests for date range helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock, patch

from guten_morgen.time_utils import (
    end_of_next_day,
    format_duration_human,
    get_local_timezone,
    parse_since,
    this_month_range,
    this_week_range,
    today_range,
)


class TestTodayRange:
    def test_returns_iso_strings(self) -> None:
        start, end = today_range()
        # Should be valid ISO strings
        datetime.fromisoformat(start)
        datetime.fromisoformat(end)

    def test_same_day(self) -> None:
        fixed = datetime(2026, 2, 17, 14, 30, 0, tzinfo=timezone.utc)
        with patch("guten_morgen.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            start, end = today_range()
        assert "2026-02-17" in start
        assert "2026-02-17" in end


class TestThisWeekRange:
    def test_returns_monday_to_sunday(self) -> None:
        # 2026-02-17 is a Tuesday
        fixed = datetime(2026, 2, 17, 14, 0, 0, tzinfo=timezone.utc)
        with patch("guten_morgen.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            start, end = this_week_range()
        assert "2026-02-16" in start  # Monday
        assert "2026-02-22" in end  # Sunday


class TestThisMonthRange:
    def test_returns_month_range(self) -> None:
        fixed = datetime(2026, 2, 17, 14, 0, 0, tzinfo=timezone.utc)
        with patch("guten_morgen.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            start, end = this_month_range()
        assert "2026-02-01" in start
        assert "2026-02-28" in end


class TestFormatDurationHuman:
    def test_minutes_only(self) -> None:
        assert format_duration_human(30) == "30m"

    def test_hours_only(self) -> None:
        assert format_duration_human(120) == "2h"

    def test_hours_and_minutes(self) -> None:
        assert format_duration_human(90) == "1h30m"

    def test_zero_minutes(self) -> None:
        assert format_duration_human(0) == "0m"


class TestEndOfNextDay:
    def test_returns_iso_string(self) -> None:
        ref = datetime(2026, 2, 17, 10, 0, 0, tzinfo=timezone.utc)
        result = end_of_next_day(ref)
        parsed = datetime.fromisoformat(result)
        assert parsed.year == 2026
        assert parsed.month == 2
        assert parsed.day == 18
        assert parsed.hour == 23
        assert parsed.minute == 59
        assert parsed.second == 59

    def test_defaults_to_now(self) -> None:
        result = end_of_next_day()
        # Should be a valid ISO string
        datetime.fromisoformat(result)


class TestGetLocalTimezone:
    def test_reads_etc_localtime(self, monkeypatch):
        """Reads timezone from /etc/localtime symlink."""
        monkeypatch.setattr("os.readlink", lambda _: "/var/db/timezone/zoneinfo/Europe/Paris")
        assert get_local_timezone() == "Europe/Paris"

    def test_falls_back_to_systemsetup(self, monkeypatch):
        """Falls back to systemsetup when /etc/localtime fails."""
        monkeypatch.setattr("os.readlink", Mock(side_effect=OSError))
        mock_result = Mock(returncode=0, stdout="Time Zone: America/New_York")
        monkeypatch.setattr("subprocess.run", Mock(return_value=mock_result))
        assert get_local_timezone() == "America/New_York"

    def test_falls_back_to_tz_env(self, monkeypatch):
        """Falls back to $TZ when both /etc/localtime and systemsetup fail."""
        monkeypatch.setattr("os.readlink", Mock(side_effect=OSError))
        monkeypatch.setattr("subprocess.run", Mock(side_effect=FileNotFoundError))
        monkeypatch.setenv("TZ", "Asia/Tokyo")
        assert get_local_timezone() == "Asia/Tokyo"

    def test_defaults_to_utc(self, monkeypatch):
        """Returns UTC when no timezone source is available."""
        monkeypatch.setattr("os.readlink", Mock(side_effect=OSError))
        monkeypatch.setattr("subprocess.run", Mock(side_effect=FileNotFoundError))
        monkeypatch.delenv("TZ", raising=False)
        assert get_local_timezone() == "UTC"

    def test_localtime_without_zoneinfo(self, monkeypatch):
        """Falls through when /etc/localtime has no zoneinfo/ in path."""
        monkeypatch.setattr("os.readlink", lambda _: "/some/other/path")
        mock_result = Mock(returncode=0, stdout="Time Zone: Europe/London")
        monkeypatch.setattr("subprocess.run", Mock(return_value=mock_result))
        assert get_local_timezone() == "Europe/London"


class TestParseSince:
    def test_days(self) -> None:
        result = parse_since("7d")
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None
        # Should be roughly 7 days ago
        diff = datetime.now(timezone.utc) - parsed
        assert 6.9 < diff.total_seconds() / 86400 < 7.1

    def test_hours(self) -> None:
        result = parse_since("2h")
        parsed = datetime.fromisoformat(result)
        diff = datetime.now(timezone.utc) - parsed
        assert 1.9 < diff.total_seconds() / 3600 < 2.1

    def test_weeks(self) -> None:
        result = parse_since("1w")
        parsed = datetime.fromisoformat(result)
        diff = datetime.now(timezone.utc) - parsed
        assert 6.9 < diff.total_seconds() / 86400 < 7.1

    def test_yesterday(self) -> None:
        result = parse_since("yesterday")
        parsed = datetime.fromisoformat(result)
        # Should be midnight yesterday
        assert parsed.hour == 0
        assert parsed.minute == 0

    def test_iso_date_passthrough(self) -> None:
        result = parse_since("2026-03-01")
        assert result == "2026-03-01"

    def test_iso_datetime_passthrough(self) -> None:
        result = parse_since("2026-03-01T10:00:00")
        assert result == "2026-03-01T10:00:00"

    def test_invalid_raises(self) -> None:
        import click
        import pytest

        with pytest.raises(click.exceptions.BadParameter):
            parse_since("banana")

    def test_whitespace_stripped(self) -> None:
        result = parse_since("  7d  ")
        parsed = datetime.fromisoformat(result)
        diff = datetime.now(timezone.utc) - parsed
        assert 6.9 < diff.total_seconds() / 86400 < 7.1

    def test_30d(self) -> None:
        result = parse_since("30d")
        parsed = datetime.fromisoformat(result)
        diff = datetime.now(timezone.utc) - parsed
        assert 29.9 < diff.total_seconds() / 86400 < 30.1


class TestComputeFreeSlots:
    def test_no_events_returns_full_window(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        slots = compute_free_slots(
            events=[],
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        assert len(slots) == 1
        assert slots[0]["start"] == "2026-02-20T09:00:00"
        assert slots[0]["end"] == "2026-02-20T18:00:00"
        assert slots[0]["duration_minutes"] == 540

    def test_one_event_splits_window(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        events = [{"start": "2026-02-20T12:00:00", "duration": "PT1H"}]
        slots = compute_free_slots(
            events=events,
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        assert len(slots) == 2
        assert slots[0]["start"] == "2026-02-20T09:00:00"
        assert slots[0]["end"] == "2026-02-20T12:00:00"
        assert slots[1]["start"] == "2026-02-20T13:00:00"
        assert slots[1]["end"] == "2026-02-20T18:00:00"

    def test_min_duration_filters_short_gaps(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        events = [
            {"start": "2026-02-20T10:00:00", "duration": "PT50M"},
            {"start": "2026-02-20T11:00:00", "duration": "PT1H"},
        ]
        slots = compute_free_slots(
            events=events,
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        # 09:00-10:00 (60m) yes, 10:50-11:00 (10m) no, 12:00-18:00 (360m) yes
        starts = [s["start"] for s in slots]
        assert "2026-02-20T09:00:00" in starts
        assert "2026-02-20T12:00:00" in starts
        assert len(slots) == 2

    def test_overlapping_events(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        events = [
            {"start": "2026-02-20T09:00:00", "duration": "PT2H"},
            {"start": "2026-02-20T10:00:00", "duration": "PT1H"},
        ]
        slots = compute_free_slots(
            events=events,
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        assert len(slots) == 1
        assert slots[0]["start"] == "2026-02-20T11:00:00"

    def test_event_before_window(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        events = [{"start": "2026-02-20T07:00:00", "duration": "PT1H"}]
        slots = compute_free_slots(
            events=events,
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        assert len(slots) == 1
        assert slots[0]["start"] == "2026-02-20T09:00:00"

    def test_event_spanning_window_start(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        events = [{"start": "2026-02-20T08:00:00", "duration": "PT2H"}]
        slots = compute_free_slots(
            events=events,
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        assert slots[0]["start"] == "2026-02-20T10:00:00"

    def test_all_day_event_ignored(self) -> None:
        from guten_morgen.time_utils import compute_free_slots

        events = [{"start": "2026-02-20", "duration": "P1D", "showWithoutTime": True}]
        slots = compute_free_slots(
            events=events,
            day="2026-02-20",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
        )
        assert len(slots) == 1
        assert slots[0]["duration_minutes"] == 540


class TestToLocalIso:
    def test_floating_time_zone_passes_through_unchanged(self) -> None:
        # No stored zone (all-day / floating) → nothing to convert, return as-is.
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("2026-06-03T10:00:00", None, "Europe/Budapest") == "2026-06-03T10:00:00"

    def test_same_zone_keeps_wall_clock_and_adds_offset(self) -> None:
        # Event already in the local zone: wall-clock unchanged, but now offset-qualified.
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("2026-06-03T10:00:00", "Europe/Budapest", "Europe/Budapest") == "2026-06-03T10:00:00+02:00"

    def test_cross_zone_summer_new_york_to_budapest(self) -> None:
        # 10:00 EDT (UTC-4) == 16:00 CEST (UTC+2).
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("2026-06-03T10:00:00", "America/New_York", "Europe/Budapest") == "2026-06-03T16:00:00+02:00"

    def test_cross_zone_winter_keeps_dst_offset(self) -> None:
        # 10:00 EST (UTC-5) == 16:00 CET (UTC+1): same wall-clock as summer, different offset.
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("2026-01-15T10:00:00", "America/New_York", "Europe/Budapest") == "2026-01-15T16:00:00+01:00"

    def test_utc_event_converts_to_local(self) -> None:
        # Imported bookings carry Etc/UTC: 14:00 UTC == 16:00 CEST.
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("2026-06-03T14:00:00", "Etc/UTC", "Europe/Budapest") == "2026-06-03T16:00:00+02:00"

    def test_accepts_start_with_trailing_fractional_noise(self) -> None:
        # Morgen sometimes appends sub-second precision; only the first 19 chars are the wall-clock.
        from guten_morgen.time_utils import to_local_iso

        assert (
            to_local_iso("2026-06-03T10:00:00.000", "America/New_York", "Europe/Budapest")
            == "2026-06-03T16:00:00+02:00"
        )

    # --- conversion to targets other than Budapest (helper is not zone-specific) ---

    def test_converts_to_new_york_target(self) -> None:
        # 16:00 CEST (UTC+2) == 10:00 EDT (UTC-4).
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("2026-06-03T16:00:00", "Europe/Budapest", "America/New_York") == "2026-06-03T10:00:00-04:00"

    def test_converts_to_tokyo_target(self) -> None:
        # 10:00 EDT (UTC-4) == 23:00 JST (UTC+9, no DST).
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("2026-06-03T10:00:00", "America/New_York", "Asia/Tokyo") == "2026-06-03T23:00:00+09:00"

    def test_converts_to_utc_target(self) -> None:
        # 10:00 EDT (UTC-4) == 14:00 UTC, rendered with a +00:00 offset.
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("2026-06-03T10:00:00", "America/New_York", "Etc/UTC") == "2026-06-03T14:00:00+00:00"

    # --- wrong / empty parameters: degrade to the raw start, never raise ---

    def test_empty_time_zone_passes_through(self) -> None:
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("2026-06-03T10:00:00", "", "Europe/Budapest") == "2026-06-03T10:00:00"

    def test_unknown_event_time_zone_degrades_to_raw(self) -> None:
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("2026-06-03T10:00:00", "Mars/Phobos", "Europe/Budapest") == "2026-06-03T10:00:00"

    def test_unknown_local_time_zone_degrades_to_raw(self) -> None:
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("2026-06-03T10:00:00", "America/New_York", "Bogus/Zone") == "2026-06-03T10:00:00"

    def test_empty_start_passes_through(self) -> None:
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("", "America/New_York", "Europe/Budapest") == ""

    def test_unparseable_start_degrades_to_raw(self) -> None:
        from guten_morgen.time_utils import to_local_iso

        assert to_local_iso("not-a-date", "America/New_York", "Europe/Budapest") == "not-a-date"


class TestComputeFreeSlotsTimezone:
    def test_cross_zone_event_blocks_local_hours_not_raw_wall_clock(self) -> None:
        # A New York event at 10:00 is 16:00 in Budapest. Availability must block 16:00-17:00
        # local, NOT the raw 10:00-11:00 wall-clock.
        from guten_morgen.time_utils import compute_free_slots

        events = [{"start": "2026-06-03T10:00:00", "duration": "PT1H", "timeZone": "America/New_York"}]
        slots = compute_free_slots(
            events=events,
            day="2026-06-03",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
            local_tz="Europe/Budapest",
        )
        intervals = {(s["start"], s["end"]) for s in slots}
        assert ("2026-06-03T09:00:00", "2026-06-03T16:00:00") in intervals
        assert ("2026-06-03T17:00:00", "2026-06-03T18:00:00") in intervals
        # The buggy behavior would have blocked 10:00-11:00, leaving a 11:00 slot start.
        assert all(s["start"] != "2026-06-03T11:00:00" for s in slots)

    def test_floating_event_still_treated_as_local(self) -> None:
        # No timeZone (floating): unchanged behavior — 14:00 blocks 14:00-16:00 local.
        from guten_morgen.time_utils import compute_free_slots

        events = [{"start": "2026-06-03T14:00:00", "duration": "PT2H"}]
        slots = compute_free_slots(
            events=events,
            day="2026-06-03",
            window_start="09:00",
            window_end="18:00",
            min_duration_minutes=30,
            local_tz="Europe/Budapest",
        )
        intervals = {(s["start"], s["end"]) for s in slots}
        assert ("2026-06-03T09:00:00", "2026-06-03T14:00:00") in intervals
        assert ("2026-06-03T16:00:00", "2026-06-03T18:00:00") in intervals
