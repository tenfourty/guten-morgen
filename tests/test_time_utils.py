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
