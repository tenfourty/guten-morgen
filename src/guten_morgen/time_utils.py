"""Date range helpers for quick views."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


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


def _parse_duration_minutes(duration: str) -> int:
    """Parse ISO 8601 duration string to minutes. Supports PTxHyM, PTxM, PTxH, PxD."""
    import re

    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration)
    if match and (match.group(1) or match.group(2)):
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        return hours * 60 + minutes
    day_match = re.match(r"P(\d+)D", duration)
    if day_match:
        return int(day_match.group(1)) * 24 * 60
    return 0


def compute_free_slots(
    events: list[dict[str, Any]],
    day: str,
    window_start: str = "09:00",
    window_end: str = "18:00",
    min_duration_minutes: int = 30,
) -> list[dict[str, Any]]:
    """Compute free time slots on a given day.

    Args:
        events: List of event dicts (need 'start', 'duration', optional 'showWithoutTime')
        day: Date string (YYYY-MM-DD)
        window_start: Working hours start (HH:MM)
        window_end: Working hours end (HH:MM)
        min_duration_minutes: Minimum slot duration to include

    Returns:
        List of dicts: [{start, end, duration_minutes}]
    """

    ws = datetime.fromisoformat(f"{day}T{window_start}:00")
    we = datetime.fromisoformat(f"{day}T{window_end}:00")

    busy: list[tuple[datetime, datetime]] = []
    for evt in events:
        if evt.get("showWithoutTime"):
            continue
        start_str = evt.get("start", "")
        dur_str = evt.get("duration", "PT0M")
        if not start_str or len(start_str) < 16:
            continue
        evt_start = datetime.fromisoformat(start_str[:19])
        evt_end = evt_start + timedelta(minutes=_parse_duration_minutes(dur_str))
        clipped_start = max(evt_start, ws)
        clipped_end = min(evt_end, we)
        if clipped_start < clipped_end:
            busy.append((clipped_start, clipped_end))

    busy.sort()
    merged: list[tuple[datetime, datetime]] = []
    for start, end in busy:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    slots: list[dict[str, Any]] = []
    cursor = ws
    for busy_start, busy_end in merged:
        if cursor < busy_start:
            gap_minutes = int((busy_start - cursor).total_seconds() / 60)
            if gap_minutes >= min_duration_minutes:
                slots.append(
                    {
                        "start": cursor.isoformat(),
                        "end": busy_start.isoformat(),
                        "duration_minutes": gap_minutes,
                    }
                )
        cursor = max(cursor, busy_end)

    if cursor < we:
        gap_minutes = int((we - cursor).total_seconds() / 60)
        if gap_minutes >= min_duration_minutes:
            slots.append(
                {
                    "start": cursor.isoformat(),
                    "end": we.isoformat(),
                    "duration_minutes": gap_minutes,
                }
            )

    return slots
