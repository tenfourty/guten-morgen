"""Date range helpers for quick views."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def end_of_next_day(ref: datetime | None = None) -> str:
    """Return ISO string for end of tomorrow (23:59:59) in UTC.

    If *ref* is given, compute relative to that instant instead of now.
    """
    now = ref if ref is not None else datetime.now(timezone.utc)
    tomorrow_end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=2) - timedelta(seconds=1)
    return tomorrow_end.isoformat()


def today_range() -> tuple[str, str]:
    """Return (start, end) ISO strings for today in UTC."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1) - timedelta(seconds=1)
    return start.isoformat(), end.isoformat()


def this_week_range() -> tuple[str, str]:
    """Return (start, end) ISO strings for this week (Mon-Sun) in UTC."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = start - timedelta(days=start.weekday())  # Monday
    end = start + timedelta(days=7) - timedelta(seconds=1)  # Sunday 23:59:59
    return start.isoformat(), end.isoformat()


def this_month_range() -> tuple[str, str]:
    """Return (start, end) ISO strings for this month in UTC."""
    now = datetime.now(timezone.utc)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Find last day of month
    if start.month == 12:
        end_date = start.replace(year=start.year + 1, month=1)
    else:
        end_date = start.replace(month=start.month + 1)
    end = end_date - timedelta(seconds=1)
    return start.isoformat(), end.isoformat()


def get_local_timezone() -> str:
    """Get the local system IANA timezone name (e.g. 'Europe/Paris')."""
    import os
    import subprocess  # nosec B404 — hardcoded macOS commands only

    # macOS: read from systemsetup or /etc/localtime symlink
    try:
        link = os.readlink("/etc/localtime")
        # /var/db/timezone/zoneinfo/Europe/Paris -> Europe/Paris
        if "zoneinfo/" in link:
            return link.split("zoneinfo/", 1)[1]
    except OSError:
        pass

    # Fallback: try systemsetup on macOS
    try:
        result = subprocess.run(  # nosec B603 B607
            ["systemsetup", "-gettimezone"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and ":" in result.stdout:
            return result.stdout.split(":", 1)[1].strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # TZ environment variable
    tz = os.environ.get("TZ")
    if tz:
        return tz

    return "UTC"


def format_duration_human(minutes: int) -> str:
    """Format duration in minutes to human-readable string."""
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining = minutes % 60
    if remaining == 0:
        return f"{hours}h"
    return f"{hours}h{remaining}m"
