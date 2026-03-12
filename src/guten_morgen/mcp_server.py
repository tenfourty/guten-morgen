"""MCP server for guten-morgen — exposes calendar and task tools via FastMCP.

Phase 1: Read-only tools (12 tools).
Phase 2: Mutation tools (11 tools) — events + tasks CRUD.
Phase 3: Tag/list CRUD (6 tools) + MCP resources (3).
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from guten_morgen.config import load_settings
from guten_morgen.groups import load_morgen_config, resolve_filter
from guten_morgen.markup import html_to_markdown
from guten_morgen.output import enrich_events, enrich_tasks, list_enriched_tasks

if TYPE_CHECKING:
    from guten_morgen.client import MorgenClient
    from guten_morgen.groups import CalendarFilter, MorgenConfig

mcp = FastMCP("guten-morgen", instructions="Calendar and task management via Morgen API.")

# ---------------------------------------------------------------------------
# Tool annotations (MCP spec metadata hints)
# ---------------------------------------------------------------------------

_READONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
_MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
_MUTATING_IDEMPOTENT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True)
_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True)

# ---------------------------------------------------------------------------
# Concise field projections
# ---------------------------------------------------------------------------

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
    # Replace participants_display with count
    participants = event.get("participants")
    if isinstance(participants, dict):
        result["participant_count"] = len([p for p in participants.values() if isinstance(p, dict)])
    else:
        result["participant_count"] = 0
    # Abbreviate ISO duration to minutes
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


# ---------------------------------------------------------------------------
# Client lifecycle (lazy singleton)
# ---------------------------------------------------------------------------

_client: MorgenClient | None = None
_morgen_config: MorgenConfig | None = None


def _get_client_and_config() -> tuple[MorgenClient, MorgenConfig]:  # pragma: no cover
    """Lazy singleton — created on first call, reused across tool invocations."""
    global _client, _morgen_config  # noqa: PLW0603
    if _client is None:
        from guten_morgen.cache import CacheStore
        from guten_morgen.client import MorgenClient as _MC
        from guten_morgen.retry import make_agent_retry_callback

        settings = load_settings()
        cache = CacheStore()
        _client = _MC(settings, cache=cache, on_retry=make_agent_retry_callback())
        _morgen_config = load_morgen_config()
    assert _morgen_config is not None  # nosec B101  # noqa: S101
    return _client, _morgen_config


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _error_json(msg: str, suggestion: str | None = None) -> str:
    """Return a JSON error response matching the kbx error contract."""
    return json.dumps({"error": msg, "suggestion": suggestion}, ensure_ascii=False)


def _filter_kwargs(cf: CalendarFilter) -> dict[str, Any]:
    """Convert CalendarFilter to kwargs for list_all_events."""
    kw: dict[str, Any] = {}
    if cf.account_keys is not None:
        kw["account_keys"] = cf.account_keys
    if cf.calendar_names is not None:
        kw["calendar_names"] = cf.calendar_names
    if cf.active_only:
        kw["active_only"] = True
    return kw


def _is_frame_event(event: dict[str, Any]) -> bool:
    """Check if an event is a Morgen scheduling frame."""
    meta = event.get("morgen.so:metadata")
    return isinstance(meta, dict) and "frameFilterMql" in meta


def _normalize_datetime_start(s: str) -> str:
    """Normalize bare date 'YYYY-MM-DD' → 'YYYY-MM-DDT00:00:00'. Full datetimes pass through."""
    return f"{s}T00:00:00" if len(s) == 10 else s


def _normalize_datetime_end(s: str) -> str:
    """Normalize bare date 'YYYY-MM-DD' → 'YYYY-MM-DDT23:59:59'. Full datetimes pass through."""
    return f"{s}T23:59:59" if len(s) == 10 else s


def _normalize_hour(h: str) -> str:
    """Normalize hour input like '9', '09', '9:30', '09:00' → 'HH:MM'."""
    h = h.strip()
    if ":" not in h:
        return f"{int(h):02d}:00"
    parts = h.split(":", 1)
    return f"{int(parts[0]):02d}:{parts[1]}"


def _resolve_filter(config: MorgenConfig, group: str | None) -> CalendarFilter:
    """Resolve a group name to a CalendarFilter."""
    return resolve_filter(config, group=group, all_calendars=(group is None))


def _fetch_enriched_events(
    client: MorgenClient,
    config: MorgenConfig,
    start: str,
    end: str,
    group: str | None = None,
    *,
    exclude_frames: bool = True,
) -> list[dict[str, Any]]:
    """Fetch events for a date range, enrich, filter frames/declined, sort."""
    cf = _resolve_filter(config, group)
    events_models = client.list_all_events(start, end, **_filter_kwargs(cf))
    events_raw: list[dict[str, Any]] = [e.model_dump(by_alias=True) for e in events_models]
    # Remove Morgen scheduling frames (metadata-based)
    events_raw = [e for e in events_raw if not _is_frame_event(e)]
    events_raw.sort(key=lambda x: x.get("start", ""))
    enriched = enrich_events(events_raw)
    # Remove declined events
    result = [e for e in enriched if e.get("my_status") != "declined"]
    # Remove frame-like events (solo/no-status) if requested
    if exclude_frames:
        result = [e for e in result if not e.get("is_frame")]
    return result


_TAG_PRIORITY: dict[str, int] = {
    "right-now": 0,
    "active": 1,
    "waiting-on": 2,
    "someday": 3,
}
_TAG_PRIORITY_UNTAGGED = 4


def _tag_sort_key(tag_ids: list[str], tag_id_to_name: dict[str, str]) -> int:
    """Return sort priority for a task based on its best tag.

    Right-Now (0) > Active (1) > Waiting-On (2) > Someday (3) > untagged (4).
    """
    best = _TAG_PRIORITY_UNTAGGED
    for tid in tag_ids:
        name = tag_id_to_name.get(tid, "")
        prio = _TAG_PRIORITY.get(name.lower(), _TAG_PRIORITY_UNTAGGED)
        if prio < best:
            best = prio
    return best


def _fetch_categorised_tasks(
    client: MorgenClient,
    start: str,
    end: str,
    max_unscheduled: int = 20,
) -> dict[str, Any]:
    """Fetch all tasks, categorise into scheduled/overdue/unscheduled, return dict with meta."""
    result = client.list_all_tasks()
    all_tags = [t.model_dump() for t in client.list_tags()]
    all_task_lists = [tl.model_dump() for tl in client.list_task_lists()]
    tasks_data = enrich_tasks(
        [t.model_dump() for t in result.tasks],
        label_defs=[ld.model_dump() for ld in result.labelDefs],
        tags=all_tags,
        task_lists=all_task_lists,
    )

    # Build tag ID→name map for sort key
    tag_id_to_name: dict[str, str] = {t["id"]: t["name"] for t in all_tags if "id" in t and "name" in t}

    scheduled: list[dict[str, Any]] = []
    overdue: list[dict[str, Any]] = []
    unscheduled: list[dict[str, Any]] = []

    start_date = start[:10]
    end_date = end[:10]
    for t in tasks_data:
        if t.get("progress") == "completed":
            continue
        due = t.get("due", "")
        if due:
            due_date = due[:10]
            if start_date <= due_date <= end_date:
                scheduled.append(t)
            elif due_date < start_date:
                overdue.append(t)
        else:
            unscheduled.append(t)

    # Sort unscheduled by tag priority (Right-Now first) before truncation
    unscheduled.sort(key=lambda t: _tag_sort_key(t.get("tags", []), tag_id_to_name))

    total_unscheduled = len(unscheduled)
    truncated = total_unscheduled > max_unscheduled

    return {
        "scheduled_tasks": [_concise_task(t) for t in scheduled],
        "overdue_tasks": [_concise_task(t) for t in overdue],
        "unscheduled_tasks": [_concise_task(t) for t in unscheduled[:max_unscheduled]],
        "meta": {
            "unscheduled_truncated": truncated,
            "unscheduled_total": total_unscheduled,
        },
    }


# ---------------------------------------------------------------------------
# Handler functions (testable without MCP transport)
# ---------------------------------------------------------------------------


def _project_events(events: list[dict[str, Any]], *, compact: bool = False) -> list[dict[str, Any]]:
    """Apply concise or compact projection to events."""
    if compact:
        return [_compact_event(e) for e in events]
    return [_concise_event(e) for e in events]


def handle_gm_today(
    client: MorgenClient,
    config: MorgenConfig,
    *,
    group: str | None = None,
    events_only: bool = False,
    tasks_only: bool = False,
    max_unscheduled: int = 20,
    exclude_frames: bool = True,
    compact: bool = False,
) -> str:
    """Combined events + tasks for today. Returns JSON string."""
    try:
        from guten_morgen.time_utils import today_range

        start, end = today_range()
        result: dict[str, Any] = {}

        if not tasks_only:
            events = _fetch_enriched_events(client, config, start, end, group, exclude_frames=exclude_frames)
            result["events"] = _project_events(events, compact=compact)

        if not events_only:
            result.update(_fetch_categorised_tasks(client, start, end, max_unscheduled))

        return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_today error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_next(
    client: MorgenClient,
    config: MorgenConfig,
    *,
    count: int = 3,
) -> str:
    """Next upcoming events. Returns JSON string."""
    try:
        from guten_morgen.time_utils import end_of_next_day

        now = datetime.now(timezone.utc)
        end = end_of_next_day(now)
        events = _fetch_enriched_events(client, config, now.isoformat(), end)
        # Filter to events starting after now
        upcoming = [e for e in events if (e.get("start") or "") >= now.isoformat()[:19]]
        if count is not None:
            upcoming = upcoming[:count]
        return json.dumps([_concise_event(e) for e in upcoming], default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_next error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_this_week(
    client: MorgenClient,
    config: MorgenConfig,
    *,
    group: str | None = None,
    events_only: bool = False,
    tasks_only: bool = False,
    max_unscheduled: int = 20,
    exclude_frames: bool = True,
    compact: bool = False,
) -> str:
    """Combined events + tasks for the current week (Mon-Sun). Returns JSON string."""
    try:
        from guten_morgen.time_utils import this_week_range

        start, end = this_week_range()
        result: dict[str, Any] = {}

        if not tasks_only:
            events = _fetch_enriched_events(client, config, start, end, group, exclude_frames=exclude_frames)
            result["events"] = _project_events(events, compact=compact)

        if not events_only:
            result.update(_fetch_categorised_tasks(client, start, end, max_unscheduled))

        return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_this_week error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_this_month(
    client: MorgenClient,
    config: MorgenConfig,
    *,
    group: str | None = None,
    events_only: bool = False,
    tasks_only: bool = False,
    max_unscheduled: int = 20,
    exclude_frames: bool = True,
    compact: bool = False,
) -> str:
    """Combined events + tasks for the current month. Returns JSON string."""
    try:
        from guten_morgen.time_utils import this_month_range

        start, end = this_month_range()
        result: dict[str, Any] = {}

        if not tasks_only:
            events = _fetch_enriched_events(client, config, start, end, group, exclude_frames=exclude_frames)
            result["events"] = _project_events(events, compact=compact)

        if not events_only:
            result.update(_fetch_categorised_tasks(client, start, end, max_unscheduled))

        return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_this_month error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_events_list(
    client: MorgenClient,
    config: MorgenConfig,
    *,
    start: str,
    end: str,
    group: str | None = None,
) -> str:
    """List events in a date range (max 90 days). Accepts bare dates (YYYY-MM-DD). Returns JSON string."""
    try:
        start = _normalize_datetime_start(start)
        end = _normalize_datetime_end(end)
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        if (end_dt - start_dt).days > 90:
            return _error_json("Date range exceeds 90 days. Use a shorter range to avoid context overflow.")
        events = _fetch_enriched_events(client, config, start, end, group)
        return json.dumps([_concise_event(e) for e in events], default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_events_list error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


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


def handle_gm_events_get(
    client: MorgenClient,
    config: MorgenConfig,
    *,
    event_id: str,
) -> str:
    """Get a single event by ID — full detail view with structured participants. Returns JSON string."""
    try:
        from datetime import timedelta

        # Search today and surrounding window (±30 days) to find the event
        start_dt = datetime.now(timezone.utc)

        search_start = (start_dt - timedelta(days=30)).isoformat()
        search_end = (start_dt + timedelta(days=30)).isoformat()

        cf = _resolve_filter(config, None)
        events_models = client.list_all_events(search_start, search_end, **_filter_kwargs(cf))

        target: dict[str, Any] | None = None
        for e in events_models:
            if e.id == event_id:
                target = e.model_dump(by_alias=True)
                break

        if target is None:
            return _error_json(f"Event '{event_id}' not found", "Check the event ID with gm_events_list")

        # Enrich
        enriched = enrich_events([target])[0]

        # Replace participants dict with structured list
        enriched["participants"] = _structured_participants(target.get("participants"))

        # Convert description HTML to markdown
        desc = enriched.get("description")
        if desc is not None:
            enriched["description"] = html_to_markdown(desc)

        # Strip None values
        enriched = {k: v for k, v in enriched.items() if v is not None}

        return json.dumps(enriched, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_events_get error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def _compute_slots_for_day(
    client: MorgenClient,
    config: MorgenConfig,
    *,
    day: str,
    min_duration_minutes: int,
    start_hour: str | None,
    end_hour: str | None,
    group: str | None,
) -> list[dict[str, Any]]:
    """Compute free slots for a single day. Used by handle_gm_availability."""
    from guten_morgen.time_utils import compute_free_slots

    cf = _resolve_filter(config, group)
    day_start = f"{day}T00:00:00"
    day_end = f"{day}T23:59:59"
    events_models = client.list_all_events(day_start, day_end, **_filter_kwargs(cf))
    events_data = [e.model_dump(by_alias=True) for e in events_models]

    return compute_free_slots(
        events=events_data,
        day=day,
        window_start=_normalize_hour(start_hour) if start_hour else "08:00",
        window_end=_normalize_hour(end_hour) if end_hour else "18:00",
        min_duration_minutes=min_duration_minutes,
    )


def handle_gm_availability(
    client: MorgenClient,
    config: MorgenConfig,
    *,
    date: str,
    min_duration_minutes: int = 30,
    start_hour: str | None = None,
    end_hour: str | None = None,
    group: str | None = None,
    end_date: str | None = None,
) -> str:
    """Find available time slots on a date (or date range). Returns JSON string."""
    try:
        if end_date is None:
            # Single-day mode — returns list of slots (unchanged behaviour)
            slots = _compute_slots_for_day(
                client,
                config,
                day=date,
                min_duration_minutes=min_duration_minutes,
                start_hour=start_hour,
                end_hour=end_hour,
                group=group,
            )
            return json.dumps(slots, default=str, ensure_ascii=False)

        # Multi-day mode
        from datetime import timedelta

        start_dt = datetime.strptime(date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        num_days = (end_dt - start_dt).days + 1
        if num_days > 14:
            return _error_json(
                f"Date range spans {num_days} days. Maximum is 14 days.",
                "Use a shorter range or make multiple requests.",
            )

        result: dict[str, list[dict[str, Any]]] = {}
        current = start_dt
        while current <= end_dt:
            day_str = current.strftime("%Y-%m-%d")
            result[day_str] = _compute_slots_for_day(
                client,
                config,
                day=day_str,
                min_duration_minutes=min_duration_minutes,
                start_hour=start_hour,
                end_hour=end_hour,
                group=group,
            )
            current += timedelta(days=1)

        return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_availability error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


_VALID_ORDER_BY = ("due_date", "tag_priority", "list_name", "title")


def _filter_tasks(
    tasks: list[dict[str, Any]],
    *,
    status: str = "open",
    overdue: bool = False,
    tag_id_filter: set[str] | None = None,
    list_id_filter: str | None = None,
    project: str | None = None,
    query: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
) -> list[dict[str, Any]]:
    """Filter tasks by status, overdue, tag, list, project, query, due_before/after.

    Shared by handle_gm_tasks_list and handle_gm_tasks_count.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    query_lower = query.lower() if query else None

    filtered: list[dict[str, Any]] = []
    for t in tasks:
        progress = t.get("progress", "")
        if status == "open" and progress == "completed":
            continue
        if status == "completed" and progress != "completed":
            continue

        if overdue:
            due = t.get("due", "")
            if not due or due[:10] >= now_iso[:10]:
                continue

        if tag_id_filter:
            task_tags = set(t.get("tags", []))
            if not task_tags & tag_id_filter:
                continue

        if list_id_filter and t.get("taskListId") != list_id_filter:
            continue

        if project:
            proj = t.get("project")
            if not proj or project.lower() not in proj.lower():
                continue

        if query_lower:
            title = (t.get("title") or "").lower()
            desc = (t.get("description") or "").lower()
            if query_lower not in title and query_lower not in desc:
                continue

        if due_before or due_after:
            due = t.get("due", "")
            if not due:
                continue
            due_date = due[:10]
            if due_before and due_date >= due_before:
                continue
            if due_after and due_date <= due_after:
                continue

        filtered.append(t)

    return filtered


def _resolve_filters(
    client: MorgenClient,
    *,
    tag: str | None = None,
    list_name: str | None = None,
) -> tuple[set[str], str | None]:
    """Resolve tag name(s) and list name to IDs for filtering."""
    tag_id_filter: set[str] = set()
    if tag:
        all_tags = [t.model_dump() for t in client.list_tags()]
        name_to_id = {t["name"].lower(): t["id"] for t in all_tags}
        for tn in tag.split(","):
            tid = name_to_id.get(tn.strip().lower())
            if tid:
                tag_id_filter.add(tid)

    list_id_filter: str | None = None
    if list_name:
        all_lists = client.list_task_lists()
        name_map = {tl.name.lower(): tl.id for tl in all_lists}
        list_id_filter = name_map.get(list_name.lower())

    return tag_id_filter, list_id_filter


def handle_gm_tasks_list(
    client: MorgenClient,
    *,
    status: str = "open",
    overdue: bool = False,
    source: str | None = None,
    tag: str | None = None,
    list_name: str | None = None,
    project: str | None = None,
    query: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    order_by: str | None = None,
    limit: int = 25,
) -> str:
    """List tasks with filtering. Returns JSON string."""
    try:
        if order_by and order_by not in _VALID_ORDER_BY:
            return _error_json(f"Invalid order_by '{order_by}'. Valid values: {', '.join(_VALID_ORDER_BY)}")

        tasks_data = list_enriched_tasks(client, source=source)
        tag_id_filter, list_id_filter = _resolve_filters(client, tag=tag, list_name=list_name)

        filtered = _filter_tasks(
            tasks_data,
            status=status,
            overdue=overdue,
            tag_id_filter=tag_id_filter or None,
            list_id_filter=list_id_filter,
            project=project,
            query=query,
            due_before=due_before,
            due_after=due_after,
        )

        # Apply sorting
        if order_by == "due_date":
            filtered.sort(key=lambda t: t.get("due") or "\xff")
        elif order_by == "tag_priority":
            all_tags = [t.model_dump() for t in client.list_tags()]
            tag_id_to_name: dict[str, str] = {t["id"]: t["name"] for t in all_tags if "id" in t and "name" in t}
            filtered.sort(key=lambda t: _tag_sort_key(t.get("tags", []), tag_id_to_name))
        elif order_by == "list_name":
            filtered.sort(key=lambda t: (t.get("list_name") or "\xff").lower())
        elif order_by == "title":
            filtered.sort(key=lambda t: (t.get("title") or "").lower())

        clamped_limit = min(max(limit, 1), 100)
        concise = [_concise_task(t) for t in filtered[:clamped_limit]]
        return json.dumps(concise, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_tasks_list error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_tasks_count(
    client: MorgenClient,
    *,
    status: str = "open",
    overdue: bool = False,
    source: str | None = None,
    tag: str | None = None,
    list_name: str | None = None,
    project: str | None = None,
    query: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
) -> str:
    """Count tasks matching filters. Returns JSON string with count and filters."""
    try:
        tasks_data = list_enriched_tasks(client, source=source)
        tag_id_filter, list_id_filter = _resolve_filters(client, tag=tag, list_name=list_name)

        filtered = _filter_tasks(
            tasks_data,
            status=status,
            overdue=overdue,
            tag_id_filter=tag_id_filter or None,
            list_id_filter=list_id_filter,
            project=project,
            query=query,
            due_before=due_before,
            due_after=due_after,
        )

        active_filters: dict[str, Any] = {}
        if status != "open":
            active_filters["status"] = status
        if overdue:
            active_filters["overdue"] = True
        if source:
            active_filters["source"] = source
        if tag:
            active_filters["tag"] = tag
        if list_name:
            active_filters["list_name"] = list_name
        if project:
            active_filters["project"] = project
        if query:
            active_filters["query"] = query
        if due_before:
            active_filters["due_before"] = due_before
        if due_after:
            active_filters["due_after"] = due_after

        return json.dumps(
            {"count": len(filtered), "filters": active_filters},
            default=str,
            ensure_ascii=False,
        )
    except Exception as e:
        print(f"gm_tasks_count error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_tasks_get(
    client: MorgenClient,
    *,
    task_id: str,
) -> str:
    """Get a single task by ID — full detail view. Returns JSON string."""
    try:
        task = client.get_task(task_id)
        data = task.model_dump()
        desc = data.get("description")
        if desc is not None:
            data["description"] = html_to_markdown(desc)

        # Enrich with tag names, list name, source info
        all_tags = [t.model_dump() for t in client.list_tags()]
        all_task_lists = [tl.model_dump() for tl in client.list_task_lists()]
        enriched = enrich_tasks([data], tags=all_tags, task_lists=all_task_lists)
        result_data = enriched[0] if enriched else data
        # Strip None values to reduce noise
        result_data = {k: v for k, v in result_data.items() if v is not None}
        return json.dumps(result_data, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_tasks_get error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        is_not_found = "not found" in str(e).lower() or "404" in str(e)
        suggestion = "Check the task ID with gm_tasks_list" if is_not_found else None
        return _error_json(str(e), suggestion)


def handle_gm_lists(client: MorgenClient) -> str:
    """List task lists (areas of focus). Returns JSON string."""
    try:
        lists = client.list_task_lists()
        data = [{"id": tl.id, "name": tl.name, "color": getattr(tl, "color", None)} for tl in lists]
        return json.dumps(data, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_lists error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_tags(client: MorgenClient) -> str:
    """List tags (lifecycle status). Returns JSON string."""
    try:
        tags = client.list_tags()
        data = [{"id": t.id, "name": t.name, "color": getattr(t, "color", None)} for t in tags]
        return json.dumps(data, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_tags error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_accounts(client: MorgenClient) -> str:
    """List connected calendar accounts. Returns JSON string."""
    try:
        accounts = client.list_accounts()
        data = [
            {
                "id": a.id,
                "name": getattr(a, "providerUserDisplayName", None),
                "email": getattr(a, "preferredEmail", None),
                "integrationId": getattr(a, "integrationId", None),
                "integrationGroups": getattr(a, "integrationGroups", None),
            }
            for a in accounts
        ]
        return json.dumps(data, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_accounts error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_groups(config: MorgenConfig) -> str:
    """List configured calendar groups. Returns JSON string."""
    try:
        result: dict[str, Any] = {
            "default_group": config.default_group,
            "groups": {
                name: {
                    "accounts": g.accounts,
                    **({"calendars": g.calendars} if g.calendars else {}),
                }
                for name, g in sorted(config.groups.items())
            },
        }
        return json.dumps(result, default=str, ensure_ascii=False)
    except Exception as e:
        print(f"gm_groups error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------


def _is_writable(cal: dict[str, Any]) -> bool:
    """Check if a calendar is writable based on myRights or writable field."""
    rights = cal.get("myRights")
    if isinstance(rights, dict):
        return bool(rights.get("mayWriteAll") or rights.get("mayWriteOwn"))
    return bool(cal.get("writable"))


def _auto_discover(client: MorgenClient) -> tuple[str, list[str]]:
    """Auto-discover first calendar account and its writable calendars."""
    accounts = client.list_accounts()
    if not accounts:
        msg = "No connected accounts found"
        raise RuntimeError(msg)

    calendar_accounts = [a for a in accounts if "calendars" in (getattr(a, "integrationGroups", None) or [])]
    account = calendar_accounts[0] if calendar_accounts else accounts[0]
    account_id: str = account.id

    calendars = client.list_calendars()
    account_cals = [c for c in calendars if c.accountId == account_id]
    # Prefer writable calendars; fall back to all if none pass the check
    writable = [c.id for c in account_cals if _is_writable(c.model_dump())]
    if not writable:
        writable = [c.id for c in account_cals]
    if not writable:
        msg = "No calendars found for account"
        raise RuntimeError(msg)
    return account_id, writable


def _normalize_due(due: str) -> str:
    """Normalize due date to 19-char ISO 8601 (YYYY-MM-DDTHH:MM:SS)."""
    if due.endswith("Z"):
        due = due[:-1]
    elif "+" in due[10:]:
        due = due[: due.index("+", 10)]
    elif len(due) > 19 and "-" in due[19:]:
        due = due[: due.index("-", 19)]
    if len(due) == 10:
        due = f"{due}T23:59:59"
    return due[:19]


def _resolve_tag_names_to_ids(client: MorgenClient, names: str) -> list[str]:
    """Resolve comma-separated tag names to IDs. Case-insensitive."""
    all_tags = [t.model_dump() for t in client.list_tags()]
    name_to_id = {t["name"].lower(): t["id"] for t in all_tags}
    return [name_to_id[n.strip().lower()] for n in names.split(",") if n.strip().lower() in name_to_id]


def _resolve_list_name_id(client: MorgenClient, name: str) -> str:
    """Resolve a task list name to its ID. Raises RuntimeError if not found."""
    all_lists = client.list_task_lists()
    name_to_id = {tl.name.lower(): tl.id for tl in all_lists}
    lid = name_to_id.get(name.lower())
    if lid is None:
        available = ", ".join(tl.name for tl in all_lists)
        msg = f"Task list '{name}' not found. Available: {available}"
        raise RuntimeError(msg)
    return lid


def _mutation_ok(action: str, **extra: Any) -> str:
    """Return a standard mutation success response."""
    return json.dumps({"status": "ok", "action": action, **extra}, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Phase 2: Mutation handler functions
# ---------------------------------------------------------------------------


def handle_gm_tasks_create(
    client: MorgenClient,
    *,
    title: str,
    due: str | None = None,
    description: str | None = None,
    tag: str | None = None,
    list_name: str | None = None,
    project: str | None = None,
    ref: str | None = None,
    priority: int | None = None,
) -> str:
    """Create a new task. Returns JSON string."""
    try:
        task_data: dict[str, Any] = {"title": title}
        if due:
            task_data["due"] = _normalize_due(due)
        if priority is not None:
            task_data["priority"] = priority

        # Build description from metadata
        desc_parts: list[str] = []
        if description:
            desc_parts.append(description)
        if project:
            desc_parts.append(f"project: {project}")
        if ref:
            desc_parts.append(f"ref: {ref}")
        if desc_parts:
            task_data["description"] = "\n".join(desc_parts)

        if tag:
            task_data["tags"] = _resolve_tag_names_to_ids(client, tag)
        if list_name:
            task_data["taskListId"] = _resolve_list_name_id(client, list_name)

        result = client.create_task(task_data)
        task_id = result.id if result else "unknown"
        return _mutation_ok("created", task_id=task_id, title=title)
    except Exception as e:
        print(f"gm_tasks_create error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_tasks_update(
    client: MorgenClient,
    *,
    task_id: str,
    title: str | None = None,
    due: str | None = None,
    description: str | None = None,
    tag: str | None = None,
    list_name: str | None = None,
    project: str | None = None,
    ref: str | None = None,
    priority: int | None = None,
) -> str:
    """Update an existing task. Returns JSON string."""
    try:
        task_data: dict[str, Any] = {"id": task_id}
        if title is not None:
            task_data["title"] = title
        if due is not None:
            task_data["due"] = _normalize_due(due)
        if priority is not None:
            task_data["priority"] = priority

        # Handle description, project, and ref — merge with existing description
        needs_desc = description is not None or project is not None or ref is not None
        if needs_desc:
            if description is not None:
                current_desc = description
            else:
                existing = client.get_task(task_id)
                current_desc = (html_to_markdown(existing.description) or "") if existing.description else ""

            # Remove existing project:/ref: lines if replacing
            if project is not None:
                current_desc = re.sub(r"(?m)^project:.*\n?", "", current_desc)
            if ref is not None:
                current_desc = re.sub(r"(?m)^ref:.*\n?", "", current_desc)
            current_desc = re.sub(r"\n{3,}", "\n\n", current_desc).strip()

            parts = [current_desc] if current_desc else []
            if project is not None and project:
                parts.append(f"project: {project}")
            if ref is not None and ref:
                parts.append(f"ref: {ref}")
            task_data["description"] = "\n".join(parts)

        if tag is not None:
            task_data["tags"] = _resolve_tag_names_to_ids(client, tag)
        if list_name is not None:
            task_data["taskListId"] = _resolve_list_name_id(client, list_name)

        client.update_task(task_data)
        return _mutation_ok("updated", task_id=task_id)
    except Exception as e:
        print(f"gm_tasks_update error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_tasks_close(
    client: MorgenClient,
    *,
    task_id: str,
) -> str:
    """Mark a task as completed. Returns JSON string."""
    try:
        client.close_task(task_id)
        return _mutation_ok("closed", task_id=task_id)
    except Exception as e:
        print(f"gm_tasks_close error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_tasks_reopen(
    client: MorgenClient,
    *,
    task_id: str,
) -> str:
    """Reopen a completed task. Returns JSON string."""
    try:
        client.reopen_task(task_id)
        return _mutation_ok("reopened", task_id=task_id)
    except Exception as e:
        print(f"gm_tasks_reopen error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_tasks_delete(
    client: MorgenClient,
    *,
    task_id: str,
) -> str:
    """Delete a task. Returns JSON string."""
    try:
        client.delete_task(task_id)
        return _mutation_ok("deleted", task_id=task_id)
    except Exception as e:
        print(f"gm_tasks_delete error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_tasks_move(
    client: MorgenClient,
    *,
    task_id: str,
    after: str | None = None,
    parent: str | None = None,
) -> str:
    """Reorder or nest a task. Returns JSON string."""
    try:
        client.move_task(task_id, after=after, parent=parent)
        return _mutation_ok("moved", task_id=task_id)
    except Exception as e:
        print(f"gm_tasks_move error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_tasks_schedule(
    client: MorgenClient,
    *,
    task_id: str,
    start: str,
    duration_minutes: int | None = None,
    timezone: str | None = None,
) -> str:
    """Schedule a task as a linked calendar event. Returns JSON string."""
    try:
        account_id, cal_ids = _auto_discover(client)
        result = client.schedule_task(
            task_id=task_id,
            start=start,
            calendar_id=cal_ids[0],
            account_id=account_id,
            duration_minutes=duration_minutes,
            timezone=timezone,
        )
        event_id = result.id if result else "unknown"
        return _mutation_ok("scheduled", task_id=task_id, event_id=event_id)
    except Exception as e:
        print(f"gm_tasks_schedule error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_events_create(
    client: MorgenClient,
    *,
    title: str,
    start: str,
    duration_minutes: int = 30,
    description: str | None = None,
    timezone: str | None = None,
) -> str:
    """Create a new calendar event. Returns JSON string."""
    try:
        account_id, cal_ids = _auto_discover(client)
        if not timezone:
            from guten_morgen.time_utils import get_local_timezone

            timezone = get_local_timezone()
        event_data: dict[str, Any] = {
            "title": title,
            "start": start,
            "duration": f"PT{duration_minutes}M",
            "calendarId": cal_ids[0],
            "accountId": account_id,
            "showWithoutTime": False,
            "timeZone": timezone,
        }
        if description:
            event_data["description"] = description
        result = client.create_event(event_data)
        event_id = result.id if result else "unknown"
        return _mutation_ok("created", event_id=event_id, title=title)
    except Exception as e:
        print(f"gm_events_create error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_events_update(
    client: MorgenClient,
    *,
    event_id: str,
    title: str | None = None,
    start: str | None = None,
    duration_minutes: int | None = None,
    description: str | None = None,
    series_mode: str | None = None,
) -> str:
    """Update an existing calendar event. Returns JSON string."""
    try:
        account_id, cal_ids = _auto_discover(client)
        event_data: dict[str, Any] = {
            "id": event_id,
            "calendarId": cal_ids[0],
            "accountId": account_id,
        }
        if title is not None:
            event_data["title"] = title
        if start is not None:
            event_data["start"] = start
        if duration_minutes is not None:
            event_data["duration"] = f"PT{duration_minutes}M"
        if description is not None:
            event_data["description"] = description
        client.update_event(event_data, series_update_mode=series_mode)
        return _mutation_ok("updated", event_id=event_id)
    except Exception as e:
        print(f"gm_events_update error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_events_delete(
    client: MorgenClient,
    *,
    event_id: str,
    series_mode: str | None = None,
) -> str:
    """Delete a calendar event. Returns JSON string."""
    try:
        account_id, cal_ids = _auto_discover(client)
        client.delete_event(
            {"id": event_id, "calendarId": cal_ids[0], "accountId": account_id},
            series_update_mode=series_mode,
        )
        return _mutation_ok("deleted", event_id=event_id)
    except Exception as e:
        print(f"gm_events_delete error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_events_rsvp(
    client: MorgenClient,
    *,
    event_id: str,
    action: str,
    comment: str | None = None,
    notify: bool = True,
    series_mode: str | None = None,
) -> str:
    """RSVP to a calendar event. Returns JSON string."""
    try:
        account_id, cal_ids = _auto_discover(client)
        client.rsvp_event(
            action=action,
            event_id=event_id,
            calendar_id=cal_ids[0],
            account_id=account_id,
            notify_organizer=notify,
            comment=comment,
            series_update_mode=series_mode,
        )
        return _mutation_ok("rsvped", event_id=event_id)
    except Exception as e:
        print(f"gm_events_rsvp error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


# ---------------------------------------------------------------------------
# Phase 3: Tag/list CRUD handler functions
# ---------------------------------------------------------------------------


def handle_gm_tags_create(
    client: MorgenClient,
    *,
    name: str,
    color: str | None = None,
) -> str:
    """Create a tag. Returns JSON string."""
    try:
        tag_data: dict[str, Any] = {"name": name}
        if color:
            tag_data["color"] = color
        result = client.create_tag(tag_data)
        if result is None:
            return _error_json("Tag created but API returned no ID — verify in Morgen.")
        return _mutation_ok("created", tag_id=result.id, name=name)
    except Exception as e:
        print(f"gm_tags_create error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_tags_update(
    client: MorgenClient,
    *,
    tag_id: str,
    name: str | None = None,
    color: str | None = None,
) -> str:
    """Update a tag. Returns JSON string."""
    try:
        if name is None and color is None:
            return _error_json("No fields to update — provide name or color.")
        tag_data: dict[str, Any] = {"id": tag_id}
        if name is not None:
            tag_data["name"] = name
        if color is not None:
            tag_data["color"] = color
        client.update_tag(tag_data)
        return _mutation_ok("updated", tag_id=tag_id)
    except Exception as e:
        print(f"gm_tags_update error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_tags_delete(
    client: MorgenClient,
    *,
    tag_id: str,
) -> str:
    """Delete a tag. Returns JSON string."""
    try:
        client.delete_tag(tag_id)
        return _mutation_ok("deleted", tag_id=tag_id)
    except Exception as e:
        print(f"gm_tags_delete error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_lists_create(
    client: MorgenClient,
    *,
    name: str,
    color: str | None = None,
) -> str:
    """Create a task list. Returns JSON string."""
    try:
        list_data: dict[str, Any] = {"name": name}
        if color:
            list_data["color"] = color
        result = client.create_task_list(list_data)
        if result is None:
            return _error_json("List created but API returned no ID — verify in Morgen.")
        return _mutation_ok("created", list_id=result.id, name=name)
    except Exception as e:
        print(f"gm_lists_create error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_lists_update(
    client: MorgenClient,
    *,
    list_id: str,
    name: str | None = None,
    color: str | None = None,
) -> str:
    """Update a task list. Returns JSON string."""
    try:
        if name is None and color is None:
            return _error_json("No fields to update — provide name or color.")
        list_data: dict[str, Any] = {"id": list_id}
        if name is not None:
            list_data["name"] = name
        if color is not None:
            list_data["color"] = color
        client.update_task_list(list_data)
        return _mutation_ok("updated", list_id=list_id)
    except Exception as e:
        print(f"gm_lists_update error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


def handle_gm_lists_delete(
    client: MorgenClient,
    *,
    list_id: str,
) -> str:
    """Delete a task list. Returns JSON string."""
    try:
        client.delete_task_list(list_id)
        return _mutation_ok("deleted", list_id=list_id)
    except Exception as e:
        print(f"gm_lists_delete error: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return _error_json(str(e))


# ---------------------------------------------------------------------------
# MCP tool wrappers (thin — delegate to handlers)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=_READONLY)
def gm_today(  # pragma: no cover
    group: str | None = None,
    events_only: bool = False,
    tasks_only: bool = False,
    max_unscheduled: int = 20,
    exclude_frames: bool = True,
    compact: bool = False,
) -> str:
    """Today's events and tasks — the daily snapshot for agent sessions.

    Returns events, scheduled tasks, overdue tasks, and unscheduled tasks.
    Unscheduled tasks are capped at max_unscheduled (default 20).
    exclude_frames: filter out solo/frame events (default True).
    compact: minimal event projection — no id, participant_count, duration_minutes.
    """
    client, config = _get_client_and_config()
    return handle_gm_today(
        client,
        config,
        group=group,
        events_only=events_only,
        tasks_only=tasks_only,
        max_unscheduled=max_unscheduled,
        exclude_frames=exclude_frames,
        compact=compact,
    )


@mcp.tool(annotations=_READONLY)
def gm_next(count: int = 3) -> str:  # pragma: no cover
    """Next upcoming events — lightweight alternative to gm_today.

    Returns a list of upcoming events from now through end of tomorrow.
    """
    client, config = _get_client_and_config()
    return handle_gm_next(client, config, count=count)


@mcp.tool(annotations=_READONLY)
def gm_this_week(  # pragma: no cover
    group: str | None = None,
    events_only: bool = False,
    tasks_only: bool = False,
    max_unscheduled: int = 20,
    exclude_frames: bool = True,
    compact: bool = False,
) -> str:
    """This week's events and tasks (Mon-Sun) — for weekly planning.

    Same shape as gm_today: events, scheduled/overdue/unscheduled tasks.
    exclude_frames: filter out solo/frame events (default True).
    compact: minimal event projection — no id, participant_count, duration_minutes.
    """
    client, config = _get_client_and_config()
    return handle_gm_this_week(
        client,
        config,
        group=group,
        events_only=events_only,
        tasks_only=tasks_only,
        max_unscheduled=max_unscheduled,
        exclude_frames=exclude_frames,
        compact=compact,
    )


@mcp.tool(annotations=_READONLY)
def gm_this_month(  # pragma: no cover
    group: str | None = None,
    events_only: bool = False,
    tasks_only: bool = False,
    max_unscheduled: int = 20,
    exclude_frames: bool = True,
    compact: bool = False,
) -> str:
    """This month's events and tasks — for monthly planning and review.

    Same shape as gm_today: events, scheduled/overdue/unscheduled tasks.
    exclude_frames: filter out solo/frame events (default True).
    compact: minimal event projection — no id, participant_count, duration_minutes.
    """
    client, config = _get_client_and_config()
    return handle_gm_this_month(
        client,
        config,
        group=group,
        events_only=events_only,
        tasks_only=tasks_only,
        max_unscheduled=max_unscheduled,
        exclude_frames=exclude_frames,
        compact=compact,
    )


@mcp.tool(annotations=_READONLY)
def gm_events_list(start: str, end: str, group: str | None = None) -> str:  # pragma: no cover
    """List events in a date range (ISO 8601 start/end).

    Returns concise enriched event list. No description bodies.
    """
    client, config = _get_client_and_config()
    return handle_gm_events_list(client, config, start=start, end=end, group=group)


@mcp.tool(annotations=_READONLY)
def gm_events_get(event_id: str) -> str:  # pragma: no cover
    """Get a single event by ID — full detail view.

    Returns all fields including description, structured participants
    ([{name, email, status, is_organiser}]), and location. Use gm_events_list
    to find event IDs first.
    """
    client, config = _get_client_and_config()
    return handle_gm_events_get(client, config, event_id=event_id)


@mcp.tool(annotations=_READONLY)
def gm_availability(  # pragma: no cover
    date: str,
    min_duration_minutes: int = 30,
    start_hour: str | None = None,
    end_hour: str | None = None,
    group: str | None = None,
    end_date: str | None = None,
) -> str:
    """Find available time slots on a given date or date range.

    Returns list of free slots (single day) or {date: [slots]} dict (multi-day).
    Default working hours: 08:00-18:00. Multi-day capped at 14 days.
    """
    client, config = _get_client_and_config()
    return handle_gm_availability(
        client,
        config,
        date=date,
        min_duration_minutes=min_duration_minutes,
        start_hour=start_hour,
        end_hour=end_hour,
        group=group,
        end_date=end_date,
    )


@mcp.tool(annotations=_READONLY)
def gm_tasks_list(  # pragma: no cover
    status: str = "open",
    overdue: bool = False,
    source: str | None = None,
    tag: str | None = None,
    list_name: str | None = None,
    project: str | None = None,
    query: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    order_by: str | None = None,
    limit: int = 25,
) -> str:
    """List tasks with filtering.

    Status: open (default), completed, all. Tag/list_name filter by name.
    query: case-insensitive text search on title and description.
    due_before/due_after: filter by due date (YYYY-MM-DD, exclusive).
    order_by: due_date, tag_priority, list_name, or title.
    Limit defaults to 25, max 100. Returns concise task list.

    Note: status="completed" only returns tasks from local cache. The Morgen API
    requires an updatedAfter parameter to return completed tasks — use gm CLI
    with --status completed --since for comprehensive results.
    """
    client, _ = _get_client_and_config()
    return handle_gm_tasks_list(
        client,
        status=status,
        overdue=overdue,
        source=source,
        tag=tag,
        list_name=list_name,
        project=project,
        query=query,
        due_before=due_before,
        due_after=due_after,
        order_by=order_by,
        limit=limit,
    )


@mcp.tool(annotations=_READONLY)
def gm_tasks_count(  # pragma: no cover
    status: str = "open",
    overdue: bool = False,
    source: str | None = None,
    tag: str | None = None,
    list_name: str | None = None,
    project: str | None = None,
    query: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
) -> str:
    """Count tasks matching filters.

    Same filters as gm_tasks_list but returns {count, filters} instead of task list.
    Useful for dashboards and quick summaries.
    """
    client, _ = _get_client_and_config()
    return handle_gm_tasks_count(
        client,
        status=status,
        overdue=overdue,
        source=source,
        tag=tag,
        list_name=list_name,
        project=project,
        query=query,
        due_before=due_before,
        due_after=due_after,
    )


@mcp.tool(annotations=_READONLY)
def gm_tasks_get(task_id: str) -> str:  # pragma: no cover
    """Get a single task by ID — full detail view including description.

    Returns all enriched fields including markdown description, refs, source info.
    """
    client, _ = _get_client_and_config()
    return handle_gm_tasks_get(client, task_id=task_id)


@mcp.tool(annotations=_READONLY)
def gm_lists() -> str:  # pragma: no cover
    """List task lists (areas of focus) — id, name, colour for each."""
    client, _ = _get_client_and_config()
    return handle_gm_lists(client)


@mcp.tool(annotations=_READONLY)
def gm_tags() -> str:  # pragma: no cover
    """List tags (lifecycle status) — id, name, colour for each."""
    client, _ = _get_client_and_config()
    return handle_gm_tags(client)


@mcp.tool(annotations=_READONLY)
def gm_accounts() -> str:  # pragma: no cover
    """List connected calendar accounts — id, name, email, integration type."""
    client, _ = _get_client_and_config()
    return handle_gm_accounts(client)


@mcp.tool(annotations=_READONLY)
def gm_groups() -> str:  # pragma: no cover
    """List configured calendar groups — shows valid group names for filtering."""
    _, config = _get_client_and_config()
    return handle_gm_groups(config)


# ---------------------------------------------------------------------------
# Phase 2: Mutation MCP tool wrappers
# ---------------------------------------------------------------------------


@mcp.tool(annotations=_MUTATING)
def gm_tasks_create(  # pragma: no cover
    title: str,
    due: str | None = None,
    description: str | None = None,
    tag: str | None = None,
    list_name: str | None = None,
    project: str | None = None,
    ref: str | None = None,
    priority: int | None = None,
) -> str:
    """Create a new task.

    Title is required. Optional: due (ISO date or datetime), tag (name),
    list_name (area of focus), project, ref (URL), priority (0-9).
    """
    client, _ = _get_client_and_config()
    return handle_gm_tasks_create(
        client,
        title=title,
        due=due,
        description=description,
        tag=tag,
        list_name=list_name,
        project=project,
        ref=ref,
        priority=priority,
    )


@mcp.tool(annotations=_MUTATING_IDEMPOTENT)
def gm_tasks_update(  # pragma: no cover
    task_id: str,
    title: str | None = None,
    due: str | None = None,
    description: str | None = None,
    tag: str | None = None,
    list_name: str | None = None,
    project: str | None = None,
    ref: str | None = None,
    priority: int | None = None,
) -> str:
    """Update an existing task.

    Only provided fields are modified. Use gm_tasks_get to see current values.
    """
    client, _ = _get_client_and_config()
    return handle_gm_tasks_update(
        client,
        task_id=task_id,
        title=title,
        due=due,
        description=description,
        tag=tag,
        list_name=list_name,
        project=project,
        ref=ref,
        priority=priority,
    )


@mcp.tool(annotations=_MUTATING_IDEMPOTENT)
def gm_tasks_close(task_id: str) -> str:  # pragma: no cover
    """Mark a task as completed."""
    client, _ = _get_client_and_config()
    return handle_gm_tasks_close(client, task_id=task_id)


@mcp.tool(annotations=_MUTATING_IDEMPOTENT)
def gm_tasks_reopen(task_id: str) -> str:  # pragma: no cover
    """Reopen a completed task."""
    client, _ = _get_client_and_config()
    return handle_gm_tasks_reopen(client, task_id=task_id)


@mcp.tool(annotations=_DESTRUCTIVE)
def gm_tasks_delete(task_id: str) -> str:  # pragma: no cover
    """Delete a task permanently."""
    client, _ = _get_client_and_config()
    return handle_gm_tasks_delete(client, task_id=task_id)


@mcp.tool(annotations=_MUTATING)
def gm_tasks_move(task_id: str, after: str | None = None, parent: str | None = None) -> str:  # pragma: no cover
    """Reorder or nest a task.

    Use after to place after another task. Use parent to nest as subtask.
    """
    client, _ = _get_client_and_config()
    return handle_gm_tasks_move(client, task_id=task_id, after=after, parent=parent)


@mcp.tool(annotations=_MUTATING)
def gm_tasks_schedule(  # pragma: no cover
    task_id: str,
    start: str,
    duration_minutes: int | None = None,
    timezone: str | None = None,
) -> str:
    """Schedule a task as a linked calendar event (timeblocking).

    Creates a calendar event linked to the task. Calendar auto-discovered.
    """
    client, _ = _get_client_and_config()
    return handle_gm_tasks_schedule(
        client, task_id=task_id, start=start, duration_minutes=duration_minutes, timezone=timezone
    )


@mcp.tool(annotations=_MUTATING)
def gm_events_create(  # pragma: no cover
    title: str,
    start: str,
    duration_minutes: int = 30,
    description: str | None = None,
    timezone: str | None = None,
) -> str:
    """Create a new calendar event.

    Calendar and account auto-discovered. Timezone defaults to system local.
    """
    client, _ = _get_client_and_config()
    return handle_gm_events_create(
        client, title=title, start=start, duration_minutes=duration_minutes, description=description, timezone=timezone
    )


@mcp.tool(annotations=_MUTATING_IDEMPOTENT)
def gm_events_update(  # pragma: no cover
    event_id: str,
    title: str | None = None,
    start: str | None = None,
    duration_minutes: int | None = None,
    description: str | None = None,
    series_mode: str | None = None,
) -> str:
    """Update an existing calendar event.

    Only provided fields are modified. series_mode: single, future, all (for recurring).
    """
    client, _ = _get_client_and_config()
    return handle_gm_events_update(
        client,
        event_id=event_id,
        title=title,
        start=start,
        duration_minutes=duration_minutes,
        description=description,
        series_mode=series_mode,
    )


@mcp.tool(annotations=_DESTRUCTIVE)
def gm_events_delete(event_id: str, series_mode: str | None = None) -> str:  # pragma: no cover
    """Delete a calendar event.

    series_mode: single (default), future, all (for recurring events).
    """
    client, _ = _get_client_and_config()
    return handle_gm_events_delete(client, event_id=event_id, series_mode=series_mode)


@mcp.tool(annotations=_MUTATING_IDEMPOTENT)
def gm_events_rsvp(  # pragma: no cover
    event_id: str,
    action: str,
    comment: str | None = None,
    notify: bool = True,
    series_mode: str | None = None,
) -> str:
    """RSVP to a calendar event.

    Action: accept, decline, or tentative. Notifies organizer by default.
    """
    client, _ = _get_client_and_config()
    return handle_gm_events_rsvp(
        client, event_id=event_id, action=action, comment=comment, notify=notify, series_mode=series_mode
    )


# ---------------------------------------------------------------------------
# Phase 3: Tag/list CRUD MCP tool wrappers
# ---------------------------------------------------------------------------


@mcp.tool(annotations=_MUTATING)
def gm_tags_create(name: str, color: str | None = None) -> str:  # pragma: no cover
    """Create a new tag (lifecycle status label)."""
    client, _ = _get_client_and_config()
    return handle_gm_tags_create(client, name=name, color=color)


@mcp.tool(annotations=_MUTATING_IDEMPOTENT)
def gm_tags_update(tag_id: str, name: str | None = None, color: str | None = None) -> str:  # pragma: no cover
    """Update an existing tag's name or colour."""
    client, _ = _get_client_and_config()
    return handle_gm_tags_update(client, tag_id=tag_id, name=name, color=color)


@mcp.tool(annotations=_DESTRUCTIVE)
def gm_tags_delete(tag_id: str) -> str:  # pragma: no cover
    """Delete a tag permanently."""
    client, _ = _get_client_and_config()
    return handle_gm_tags_delete(client, tag_id=tag_id)


@mcp.tool(annotations=_MUTATING)
def gm_lists_create(name: str, color: str | None = None) -> str:  # pragma: no cover
    """Create a new task list (area of focus)."""
    client, _ = _get_client_and_config()
    return handle_gm_lists_create(client, name=name, color=color)


@mcp.tool(annotations=_MUTATING_IDEMPOTENT)
def gm_lists_update(list_id: str, name: str | None = None, color: str | None = None) -> str:  # pragma: no cover
    """Update an existing task list's name or colour."""
    client, _ = _get_client_and_config()
    return handle_gm_lists_update(client, list_id=list_id, name=name, color=color)


@mcp.tool(annotations=_DESTRUCTIVE)
def gm_lists_delete(list_id: str) -> str:  # pragma: no cover
    """Delete a task list permanently."""
    client, _ = _get_client_and_config()
    return handle_gm_lists_delete(client, list_id=list_id)


# ---------------------------------------------------------------------------
# MCP resources
# ---------------------------------------------------------------------------


@mcp.resource("gm://lists")
def resource_lists() -> str:  # pragma: no cover
    """Task lists (areas of focus) — id, name, colour."""
    client, _ = _get_client_and_config()
    return handle_gm_lists(client)


@mcp.resource("gm://tags")
def resource_tags() -> str:  # pragma: no cover
    """Tags (lifecycle status) — id, name, colour."""
    client, _ = _get_client_and_config()
    return handle_gm_tags(client)


@mcp.resource("gm://groups")
def resource_groups() -> str:  # pragma: no cover
    """Calendar groups — configured group names and their accounts."""
    _, config = _get_client_and_config()
    return handle_gm_groups(config)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

_PROXY_VARS = (
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "FTP_PROXY",
    "ftp_proxy",
    "GRPC_PROXY",
    "grpc_proxy",
    "RSYNC_PROXY",
)


def main() -> None:  # pragma: no cover
    """Run the MCP server on stdio transport."""
    # Strip proxy env vars injected by Claude Code sandbox (breaks httpx)
    for var in _PROXY_VARS:
        os.environ.pop(var, None)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
