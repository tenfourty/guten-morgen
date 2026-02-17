"""Tests for date range helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from morgen.time_utils import (
    format_duration_human,
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
        with patch("morgen.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            start, end = today_range()
        assert "2026-02-17" in start
        assert "2026-02-17" in end


class TestThisWeekRange:
    def test_returns_monday_to_sunday(self) -> None:
        # 2026-02-17 is a Tuesday
        fixed = datetime(2026, 2, 17, 14, 0, 0, tzinfo=timezone.utc)
        with patch("morgen.time_utils.datetime") as mock_dt:
            mock_dt.now.return_value = fixed
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            start, end = this_week_range()
        assert "2026-02-16" in start  # Monday
        assert "2026-02-22" in end  # Sunday


class TestThisMonthRange:
    def test_returns_month_range(self) -> None:
        fixed = datetime(2026, 2, 17, 14, 0, 0, tzinfo=timezone.utc)
        with patch("morgen.time_utils.datetime") as mock_dt:
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
