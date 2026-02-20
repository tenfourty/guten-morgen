"""Tests for date range helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock, patch

from guten_morgen.time_utils import (
    end_of_next_day,
    format_duration_human,
    get_local_timezone,
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
