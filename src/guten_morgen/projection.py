"""Projection helpers — pure, MCP-free.

These helpers project enriched event/task dicts down to compact or concise field sets,
and convert JSCalendar participant dicts into a structured list. They have NO dependency
on the optional `mcp` package so they are safe to import from `cli.py` regardless of
whether the `[mcp]` extra is installed.
"""

from __future__ import annotations

from typing import Any

_EVENT_CONCISE_FIELDS = frozenset(
    {"id", "title", "start", "duration", "my_status", "participants_display", "location_display"}
)
_COMPACT_EVENT_FIELDS = frozenset({"title", "start", "my_status", "location_display"})
_TASK_CONCISE_FIELDS = frozenset({"id", "title", "due", "source", "tag_names", "list_name", "project"})


def _concise_event(event: dict[str, Any]) -> dict[str, Any]:
    """Project an event dict down to the concise field set."""
    return {k: v for k, v in event.items() if k in _EVENT_CONCISE_FIELDS}


def _compact_event(event: dict[str, Any]) -> dict[str, Any]:
    """Project an event dict to compact form: no id, participant_count, duration_minutes."""
    result = {k: v for k, v in event.items() if k in _COMPACT_EVENT_FIELDS}
    participants = event.get("participants")
    if isinstance(participants, dict):
        result["participant_count"] = len([p for p in participants.values() if isinstance(p, dict)])
    else:
        result["participant_count"] = 0
    duration = event.get("duration", "")
    if isinstance(duration, str) and duration.startswith("PT"):
        minutes = 0
        dur = duration[2:]
        if "H" in dur:
            h_part, dur = dur.split("H", 1)
            minutes += int(h_part) * 60
        if "M" in dur:
            m_part = dur.split("M", 1)[0]
            minutes += int(m_part)
        result["duration_minutes"] = minutes
    return result


def _concise_task(task: dict[str, Any]) -> dict[str, Any]:
    """Project a task dict down to the concise field set."""
    return {k: v for k, v in task.items() if k in _TASK_CONCISE_FIELDS}


def _compact_task(task: dict[str, Any]) -> dict[str, Any]:
    """Project a task dict to compact form: concise fields, no id, strip nulls."""
    return {k: v for k, v in task.items() if k in _TASK_CONCISE_FIELDS and k != "id" and v is not None}


def _structured_participants(participants: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Convert JSCalendar participants dict to a structured list.

    Filters out resource-type participants (rooms, equipment).
    Returns [{name, email, status, is_organiser}].
    """
    if not participants:
        return []
    result: list[dict[str, Any]] = []
    for p in participants.values():
        if not isinstance(p, dict):
            continue
        if p.get("kind") == "resource":
            continue
        result.append(
            {
                "name": p.get("name") or p.get("email", ""),
                "email": p.get("email", ""),
                "status": p.get("participationStatus", ""),
                "is_organiser": bool(p.get("accountOwner")),
            }
        )
    return result
