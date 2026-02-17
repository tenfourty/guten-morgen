"""CLI entry point for morgen — Morgen calendar and task management."""

from __future__ import annotations

import functools
import json
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from morgen.cache import CacheStore
    from morgen.client import MorgenClient

import click

from morgen.config import load_settings
from morgen.errors import MorgenError, output_error
from morgen.groups import CalendarFilter, load_morgen_config, resolve_filter
from morgen.output import render

# ---------------------------------------------------------------------------
# Shared output options decorator
# ---------------------------------------------------------------------------


def output_options(f: Callable[..., Any]) -> Callable[..., Any]:
    """Shared decorator that adds --format, --json, --fields, --jq, --response-format to a command."""

    @click.option(
        "--format", "fmt", type=click.Choice(["table", "json", "jsonl", "csv"]), default="table", help="Output format."
    )
    @click.option("--json", "json_flag", is_flag=True, help="Shortcut for --format json.")
    @click.option("--fields", "fields_str", default=None, help="Comma-separated field list.")
    @click.option("--jq", "jq_expr", default=None, help="jq expression for filtering.")
    @click.option(
        "--response-format",
        "response_format",
        type=click.Choice(["detailed", "concise"]),
        default="detailed",
        help="Response verbosity: concise for ~1/3 tokens.",
    )
    @click.option("--short-ids", is_flag=True, default=False, help="Truncate IDs to 12 chars.")
    @click.option("--no-frames", is_flag=True, default=False, help="Exclude Morgen scheduling frames.")
    @functools.wraps(f)
    def wrapper(
        *args: Any,
        fmt: str,
        json_flag: bool,
        fields_str: str | None,
        jq_expr: str | None,
        response_format: str,
        short_ids: bool,
        no_frames: bool,
        **kwargs: Any,
    ) -> Any:
        # short_ids and no_frames are read from click context where needed
        _ = short_ids
        _ = no_frames
        if json_flag:
            fmt = "json"
        fields = [s.strip() for s in fields_str.split(",")] if fields_str else None
        kwargs["fmt"] = fmt
        kwargs["fields"] = fields
        kwargs["jq_expr"] = jq_expr
        kwargs["response_format"] = response_format
        return f(*args, **kwargs)

    return wrapper


def morgen_output(
    data: Any,
    fmt: str = "table",
    fields: list[str] | None = None,
    jq_expr: str | None = None,
    columns: list[str] | None = None,
) -> None:
    """Render data to stdout, applying --short-ids if active."""
    ctx = click.get_current_context(silent=True)
    if ctx and ctx.params.get("short_ids"):
        from morgen.output import truncate_ids

        data = truncate_ids(data)
    text = render(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=columns)
    click.echo(text)


# ---------------------------------------------------------------------------
# Calendar group filtering
# ---------------------------------------------------------------------------


def calendar_filter_options(f: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator adding --group and --all-calendars options."""

    @click.option("--group", "group_name", default=None, help="Calendar group name (from .config.toml), or 'all'.")
    @click.option("--all-calendars", is_flag=True, default=False, help="Include inactive calendars.")
    @functools.wraps(f)
    def wrapper(*args: Any, group_name: str | None, all_calendars: bool, **kwargs: Any) -> Any:
        kwargs["group_name"] = group_name
        kwargs["all_calendars"] = all_calendars
        return f(*args, **kwargs)

    return wrapper


def _resolve_calendar_filter(group_name: str | None = None, all_calendars: bool = False) -> CalendarFilter:
    """Load config and resolve to a CalendarFilter."""
    config = load_morgen_config()
    return resolve_filter(config, group=group_name, all_calendars=all_calendars)


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


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.option("--no-cache", is_flag=True, help="Bypass cache, fetch fresh from API.")
@click.pass_context
def cli(ctx: click.Context, no_cache: bool) -> None:
    """Morgen CLI — calendar and task management for Control Tower."""
    ctx.ensure_object(dict)
    ctx.obj["no_cache"] = no_cache


# ---------------------------------------------------------------------------
# usage
# ---------------------------------------------------------------------------


@cli.command()
def usage() -> None:
    """Self-documentation for AI agents."""
    config = load_morgen_config()
    config_path = _config_file_path()

    groups_section = ""
    if config.groups:
        lines: list[str] = []
        for name, g in sorted(config.groups.items()):
            line = f"  - **{name}**: accounts={g.accounts}"
            if g.calendars:
                line += f", calendars={g.calendars}"
            lines.append(line)
        groups_section = "\n".join(lines)
    else:
        groups_section = "  (none configured)"

    text = f"""# morgen — Calendar & Task Management CLI

## Commands

### Accounts & Calendars
- `morgen accounts [--json]`
  List connected calendar accounts.

- `morgen calendars [--json]`
  List all calendars across accounts.

### Events
- `morgen events list --start ISO --end ISO [--group NAME] [--all-calendars] [--json]`
  List events in a date range. Auto-discovers account/calendar.

- `morgen events create --title TEXT --start ISO --duration MINUTES [--calendar-id ID] [--description TEXT]`
  Create a new event.

- `morgen events update ID [--title TEXT] [--start ISO] [--duration MINUTES] [--description TEXT]`
  Update an existing event.

- `morgen events delete ID`
  Delete an event.

### Tasks
- `morgen tasks list [--limit N] [--status open|completed|all] [--overdue] [--json]`
  `  [--due-before ISO] [--due-after ISO] [--priority N]`
  List tasks. Filters combine with AND logic.

- `morgen tasks get ID [--json]`
  Get a single task by ID.

- `morgen tasks create --title TEXT [--due ISO] [--priority 0-4] [--description TEXT]`
  Create a new task.

- `morgen tasks update ID [--title TEXT] [--due ISO] [--priority 0-4] [--description TEXT]`
  Update a task.

- `morgen tasks close ID`
  Mark a task as completed.

- `morgen tasks reopen ID`
  Reopen a completed task.

- `morgen tasks move ID [--after TASK_ID] [--parent TASK_ID]`
  Reorder or nest a task.

- `morgen tasks delete ID`
  Delete a task.

### Tags
- `morgen tags list [--json]`
  List all tags.

- `morgen tags get ID [--json]`
  Get a single tag.

- `morgen tags create --name TEXT [--color HEX]`
  Create a tag.

- `morgen tags update ID [--name TEXT] [--color HEX]`
  Update a tag.

- `morgen tags delete ID`
  Delete a tag.

### Quick Views
- `morgen today [--json] [--response-format concise] [--events-only] [--tasks-only] [--group NAME]`
  Combined events + tasks for today. Returns categorised output:
  events, scheduled_tasks, overdue_tasks, unscheduled_tasks.

- `morgen this-week [--json] [--response-format concise] [--events-only] [--tasks-only] [--group NAME]`
  Combined events + tasks for this week (Mon-Sun). Same categories.

- `morgen this-month [--json] [--response-format concise] [--events-only] [--tasks-only] [--group NAME]`
  Combined events + tasks for this month. Same categories.

- `morgen next [--count N] [--hours N] [--json] [--response-format concise] [--group NAME]`
  Show next N upcoming events (default: 3, look-ahead: 24h).
  Much cheaper than `today` for "what's next?" queries.

### Calendar Groups
- `morgen groups [--json]`
  Show configured calendar groups and config file path.

## Global Options
- `--format table|json|jsonl|csv` (default: table)
- `--json` (shortcut for --format json)
- `--fields <comma-separated>` (select specific fields)
- `--jq <expression>` (jq filtering)
- `--response-format detailed|concise` (concise uses ~1/3 tokens)
- `--short-ids` (truncate IDs to 12 chars, saves tokens)
- `--no-frames` (exclude Morgen scheduling frames/time-blocking windows)
- `--no-cache` (bypass cache, fetch fresh from API)
- `--group NAME` (filter events by calendar group; use 'all' for no filtering)
- `--all-calendars` (include inactive calendars, overrides active_only config)

### Cache Management
- `morgen cache clear`
  Wipe all cached API data.

- `morgen cache stats`
  Show cache ages, TTLs, and sizes.

## Calendar Groups

Config file: `{config_path}`
Default group: `{config.default_group or "(none)"}`
Active-only: `{config.active_only}`

Configured groups:
{groups_section}

## Recommended Agent Workflow
1. `morgen next --json --response-format concise --no-frames`  (what's coming up?)
2. `morgen today --json --response-format concise --no-frames` (full daily overview)
3. `morgen tasks list --status open --overdue --json`  (overdue tasks)
4. `morgen tasks create --title "..." --due ...`       (create task)
5. `morgen tasks close <id>`                           (complete task)
"""
    click.echo(text)


def _config_file_path() -> str:
    """Return the resolved config file path for display."""
    import os

    from morgen.groups import _PROJECT_ROOT

    env_path = os.environ.get("MORGEN_CONFIG")
    if env_path:
        return env_path
    return str(_PROJECT_ROOT / ".config.toml")


def _get_cache_store() -> CacheStore:
    """Return a CacheStore instance (default location)."""
    from morgen.cache import CacheStore

    return CacheStore()


def _get_client() -> MorgenClient:
    """Create a MorgenClient from settings, with cache by default."""
    from morgen.client import MorgenClient

    settings = load_settings()
    ctx = click.get_current_context(silent=True)
    no_cache = ctx.obj.get("no_cache", False) if ctx and ctx.obj else False
    cache = None if no_cache else _get_cache_store()
    return MorgenClient(settings, cache=cache)


# ---------------------------------------------------------------------------
# accounts
# ---------------------------------------------------------------------------

ACCOUNT_COLUMNS = ["id", "providerUserDisplayName", "preferredEmail", "integrationId", "integrationGroups"]
ACCOUNT_CONCISE_FIELDS = ["id", "providerUserDisplayName", "integrationId"]


@cli.command()
@output_options
def accounts(fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str) -> None:
    """List connected calendar accounts."""
    try:
        client = _get_client()
        data = client.list_accounts()
        if response_format == "concise" and not fields:
            fields = ACCOUNT_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=ACCOUNT_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


# ---------------------------------------------------------------------------
# calendars
# ---------------------------------------------------------------------------

CALENDAR_COLUMNS = ["id", "accountId", "name", "color", "myRights"]
CALENDAR_CONCISE_FIELDS = ["id", "name", "myRights"]


@cli.command()
@output_options
def calendars(fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str) -> None:
    """List all calendars across accounts."""
    try:
        client = _get_client()
        data = client.list_calendars()
        if response_format == "concise" and not fields:
            fields = CALENDAR_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=CALENDAR_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------

EVENT_COLUMNS = ["id", "title", "start", "duration", "participants_display", "location_display", "calendarId"]
EVENT_CONCISE_FIELDS = ["id", "title", "start", "duration", "participants_display", "location_display"]


def _is_frame_event(event: dict[str, Any]) -> bool:
    """Check if an event is a Morgen scheduling frame (time-blocking window)."""
    meta = event.get("morgen.so:metadata")
    return isinstance(meta, dict) and "frameFilterMql" in meta


@cli.group()
def events() -> None:
    """Manage calendar events."""


def _is_writable(cal: dict[str, Any]) -> bool:
    """Check if a calendar is writable based on myRights or writable field."""
    rights = cal.get("myRights")
    if isinstance(rights, dict):
        return bool(rights.get("mayWriteAll") or rights.get("mayWriteOwn"))
    # Legacy or mock data fallback
    return bool(cal.get("writable"))


def _auto_discover(client: MorgenClient) -> tuple[str, list[str]]:
    """Auto-discover first calendar account and its writable calendars.

    Accounts use "id" field. Calendars use "id" for calendar ID,
    "accountId" to link to account, and "myRights" for permissions.
    Only picks accounts in the "calendars" integration group.
    """
    accounts_data = client.list_accounts()
    if not accounts_data:
        raise MorgenError("No connected accounts found", suggestions=["Connect an account in Morgen"])

    # Find the first calendar-capable account
    calendar_accounts = [a for a in accounts_data if "calendars" in a.get("integrationGroups", [])]
    account = calendar_accounts[0] if calendar_accounts else accounts_data[0]
    account_id: str = account.get("id", account.get("accountId", ""))

    calendars_data = client.list_calendars()
    # Filter to calendars belonging to this account
    account_cals = [c for c in calendars_data if c.get("accountId") == account_id]
    # Prefer writable calendars (myRights is a dict with mayWriteAll, mayWriteOwn, etc.)
    writable = [c.get("id", c.get("calendarId", "")) for c in account_cals if _is_writable(c)]
    if not writable:
        # Fall back to all calendars for the account
        writable = [c.get("id", c.get("calendarId", "")) for c in account_cals]
    if not writable:
        raise MorgenError("No calendars found for account", suggestions=["Check calendar sync in Morgen"])
    return account_id, writable


@events.command("list")
@click.option("--start", required=True, help="Start datetime (ISO 8601).")
@click.option("--end", required=True, help="End datetime (ISO 8601).")
@click.option("--account-id", default=None, help="Account ID (auto-discovered if omitted).")
@click.option("--calendar-id", "calendar_ids_str", default=None, help="Comma-separated calendar IDs.")
@output_options
@calendar_filter_options
def events_list(
    start: str,
    end: str,
    account_id: str | None,
    calendar_ids_str: str | None,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
    group_name: str | None,
    all_calendars: bool,
) -> None:
    """List events in a date range."""
    try:
        client = _get_client()
        if account_id and calendar_ids_str:
            cal_ids = [s.strip() for s in calendar_ids_str.split(",")]
            data = client.list_events(account_id, cal_ids, start, end)
        else:
            cf = _resolve_calendar_filter(group_name, all_calendars)
            data = client.list_all_events(start, end, **_filter_kwargs(cf))
        ctx = click.get_current_context(silent=True)
        if ctx and ctx.params.get("no_frames"):
            data = [e for e in data if not _is_frame_event(e)]
        from morgen.output import enrich_events

        data = enrich_events(data)
        if response_format == "concise" and not fields:
            fields = EVENT_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=EVENT_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@events.command("create")
@click.option("--title", required=True, help="Event title.")
@click.option("--start", required=True, help="Start datetime (ISO 8601).")
@click.option("--duration", required=True, type=int, help="Duration in minutes.")
@click.option("--calendar-id", default=None, help="Calendar ID (auto-discovered if omitted).")
@click.option("--account-id", default=None, help="Account ID (auto-discovered if omitted).")
@click.option("--description", default=None, help="Event description.")
@click.option("--timezone", default=None, help="Time zone (e.g. Europe/Paris). Defaults to system timezone.")
def events_create(
    title: str,
    start: str,
    duration: int,
    calendar_id: str | None,
    account_id: str | None,
    description: str | None,
    timezone: str | None,
) -> None:
    """Create a new event."""
    try:
        client = _get_client()
        if not account_id or not calendar_id:
            account_id, cal_ids = _auto_discover(client)
            calendar_id = calendar_id or cal_ids[0]
        if not timezone:
            from morgen.time_utils import get_local_timezone

            timezone = get_local_timezone()
        event_data: dict[str, Any] = {
            "title": title,
            "start": start,
            "duration": f"PT{duration}M",
            "calendarId": calendar_id,
            "accountId": account_id,
            "showWithoutTime": False,
            "timeZone": timezone,
        }
        if description:
            event_data["description"] = description
        result = client.create_event(event_data)
        click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@events.command("update")
@click.argument("event_id")
@click.option("--title", default=None, help="New title.")
@click.option("--start", default=None, help="New start datetime (ISO 8601).")
@click.option("--duration", default=None, type=int, help="New duration in minutes.")
@click.option("--description", default=None, help="New description.")
@click.option("--calendar-id", default=None, help="Calendar ID.")
@click.option("--account-id", default=None, help="Account ID.")
def events_update(
    event_id: str,
    title: str | None,
    start: str | None,
    duration: int | None,
    description: str | None,
    calendar_id: str | None,
    account_id: str | None,
) -> None:
    """Update an existing event."""
    try:
        client = _get_client()
        if not account_id or not calendar_id:
            account_id, cal_ids = _auto_discover(client)
            calendar_id = calendar_id or cal_ids[0]
        event_data: dict[str, Any] = {
            "id": event_id,
            "calendarId": calendar_id,
            "accountId": account_id,
        }
        if title is not None:
            event_data["title"] = title
        if start is not None:
            event_data["start"] = start
        if duration is not None:
            event_data["duration"] = f"PT{duration}M"
        if description is not None:
            event_data["description"] = description
        result = client.update_event(event_data)
        output = result or {"status": "updated", "id": event_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@events.command("delete")
@click.argument("event_id")
@click.option("--calendar-id", default=None, help="Calendar ID.")
@click.option("--account-id", default=None, help="Account ID.")
def events_delete(event_id: str, calendar_id: str | None, account_id: str | None) -> None:
    """Delete an event."""
    try:
        client = _get_client()
        if not account_id or not calendar_id:
            account_id, cal_ids = _auto_discover(client)
            calendar_id = calendar_id or cal_ids[0]
        client.delete_event({"id": event_id, "calendarId": calendar_id, "accountId": account_id})
        click.echo(json.dumps({"status": "deleted", "id": event_id}))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------

TASK_COLUMNS = ["id", "title", "progress", "priority", "due", "taskListId"]
TASK_CONCISE_FIELDS = ["id", "title", "progress", "due"]


@cli.group()
def tasks() -> None:
    """Manage tasks."""


@tasks.command("list")
@click.option("--limit", default=100, type=int, help="Max number of tasks to return.")
@click.option(
    "--status",
    "status_filter",
    type=click.Choice(["open", "completed", "all"]),
    default="all",
    help="Filter by status (default: all).",
)
@click.option("--due-before", default=None, help="Tasks due before this date (ISO 8601 or YYYY-MM-DD).")
@click.option("--due-after", default=None, help="Tasks due after this date (ISO 8601 or YYYY-MM-DD).")
@click.option("--overdue", is_flag=True, default=False, help="Show only overdue tasks (due before now).")
@click.option("--priority", "priority_filter", default=None, type=int, help="Filter by priority level (0-4).")
@output_options
def tasks_list(
    limit: int,
    status_filter: str,
    due_before: str | None,
    due_after: str | None,
    overdue: bool,
    priority_filter: int | None,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
) -> None:
    """List tasks."""
    try:
        client = _get_client()
        data = client.list_tasks(limit=limit)

        # Apply client-side filters
        if overdue:
            from datetime import datetime, timezone

            due_before = datetime.now(timezone.utc).isoformat()

        filtered: list[dict[str, Any]] = []
        for t in data:
            # Status filter
            progress = t.get("progress", "")
            if status_filter == "open" and progress == "completed":
                continue
            if status_filter == "completed" and progress != "completed":
                continue

            # Due date filters
            due = t.get("due", "")
            if due_before and due:
                if due[:10] >= due_before[:10]:
                    continue
            if due_after and due:
                if due[:10] <= due_after[:10]:
                    continue
            # If due_before or due_after specified and task has no due date, skip it
            if (due_before or due_after) and not due:
                continue

            # Priority filter
            if priority_filter is not None and t.get("priority") != priority_filter:
                continue

            filtered.append(t)

        if response_format == "concise" and not fields:
            fields = TASK_CONCISE_FIELDS
        morgen_output(filtered, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=TASK_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("get")
@click.argument("task_id")
@output_options
def tasks_get(
    task_id: str,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
) -> None:
    """Get a single task by ID."""
    try:
        client = _get_client()
        data = client.get_task(task_id)
        if response_format == "concise" and not fields:
            fields = TASK_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("create")
@click.option("--title", required=True, help="Task title.")
@click.option("--due", default=None, help="Due datetime (ISO 8601).")
@click.option("--priority", default=None, type=int, help="Priority (0-4).")
@click.option("--description", default=None, help="Task description.")
def tasks_create(
    title: str,
    due: str | None,
    priority: int | None,
    description: str | None,
) -> None:
    """Create a new task."""
    try:
        client = _get_client()
        task_data: dict[str, Any] = {"title": title}
        if due:
            task_data["due"] = due
        if priority is not None:
            task_data["priority"] = priority
        if description:
            task_data["description"] = description
        result = client.create_task(task_data)
        click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("update")
@click.argument("task_id")
@click.option("--title", default=None, help="New title.")
@click.option("--due", default=None, help="New due datetime (ISO 8601).")
@click.option("--priority", default=None, type=int, help="New priority (0-4).")
@click.option("--description", default=None, help="New description.")
def tasks_update(
    task_id: str,
    title: str | None,
    due: str | None,
    priority: int | None,
    description: str | None,
) -> None:
    """Update a task."""
    try:
        client = _get_client()
        task_data: dict[str, Any] = {"id": task_id}
        if title is not None:
            task_data["title"] = title
        if due is not None:
            task_data["due"] = due
        if priority is not None:
            task_data["priority"] = priority
        if description is not None:
            task_data["description"] = description
        result = client.update_task(task_data)
        output = result or {"status": "updated", "id": task_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("close")
@click.argument("task_id")
def tasks_close(task_id: str) -> None:
    """Mark a task as completed."""
    try:
        client = _get_client()
        result = client.close_task(task_id)
        click.echo(json.dumps(result or {"status": "closed", "id": task_id}, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("reopen")
@click.argument("task_id")
def tasks_reopen(task_id: str) -> None:
    """Reopen a completed task."""
    try:
        client = _get_client()
        result = client.reopen_task(task_id)
        output = result or {"status": "reopened", "id": task_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("move")
@click.argument("task_id")
@click.option("--after", default=None, help="Place after this task ID.")
@click.option("--parent", default=None, help="Nest under this parent task ID.")
def tasks_move(task_id: str, after: str | None, parent: str | None) -> None:
    """Reorder or nest a task."""
    try:
        client = _get_client()
        result = client.move_task(task_id, after=after, parent=parent)
        click.echo(json.dumps(result or {"status": "moved", "id": task_id}, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("delete")
@click.argument("task_id")
def tasks_delete(task_id: str) -> None:
    """Delete a task."""
    try:
        client = _get_client()
        client.delete_task(task_id)
        click.echo(json.dumps({"status": "deleted", "id": task_id}))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


# ---------------------------------------------------------------------------
# tags
# ---------------------------------------------------------------------------

TAG_COLUMNS = ["id", "name", "color"]
TAG_CONCISE_FIELDS = ["id", "name"]


@cli.group()
def tags() -> None:
    """Manage tags."""


@tags.command("list")
@output_options
def tags_list(fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str) -> None:
    """List all tags."""
    try:
        client = _get_client()
        data = client.list_tags()
        if response_format == "concise" and not fields:
            fields = TAG_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=TAG_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tags.command("get")
@click.argument("tag_id")
@output_options
def tags_get(
    tag_id: str,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
) -> None:
    """Get a single tag by ID."""
    try:
        client = _get_client()
        data = client.get_tag(tag_id)
        if response_format == "concise" and not fields:
            fields = TAG_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tags.command("create")
@click.option("--name", required=True, help="Tag name.")
@click.option("--color", default=None, help="Tag color (hex).")
def tags_create(name: str, color: str | None) -> None:
    """Create a tag."""
    try:
        client = _get_client()
        tag_data: dict[str, Any] = {"name": name}
        if color:
            tag_data["color"] = color
        result = client.create_tag(tag_data)
        click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tags.command("update")
@click.argument("tag_id")
@click.option("--name", default=None, help="New tag name.")
@click.option("--color", default=None, help="New tag color (hex).")
def tags_update(tag_id: str, name: str | None, color: str | None) -> None:
    """Update a tag."""
    try:
        client = _get_client()
        tag_data: dict[str, Any] = {"id": tag_id}
        if name is not None:
            tag_data["name"] = name
        if color is not None:
            tag_data["color"] = color
        result = client.update_tag(tag_data)
        click.echo(json.dumps(result or {"status": "updated", "id": tag_id}, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tags.command("delete")
@click.argument("tag_id")
def tags_delete(tag_id: str) -> None:
    """Delete a tag."""
    try:
        client = _get_client()
        client.delete_tag(tag_id)
        click.echo(json.dumps({"status": "deleted", "id": tag_id}))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


# ---------------------------------------------------------------------------
# next — upcoming events
# ---------------------------------------------------------------------------


def _now_utc() -> Any:
    """Return current UTC datetime. Separated for test patching."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


@cli.command()
@click.option("--count", default=None, type=int, help="Limit number of events returned.")
@output_options
@calendar_filter_options
def next(
    count: int | None,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
    group_name: str | None,
    all_calendars: bool,
) -> None:
    """Show upcoming events from now through end of tomorrow."""
    from morgen.time_utils import end_of_next_day

    try:
        client = _get_client()
        cf = _resolve_calendar_filter(group_name, all_calendars)

        now = _now_utc()
        end = end_of_next_day(now)

        events_data = client.list_all_events(now.isoformat(), end, **_filter_kwargs(cf))

        # Filter to events starting after now
        upcoming = [e for e in events_data if e.get("start", "") >= now.isoformat()[:19]]
        ctx = click.get_current_context(silent=True)
        if ctx and ctx.params.get("no_frames"):
            upcoming = [e for e in upcoming if not _is_frame_event(e)]
        upcoming.sort(key=lambda x: x.get("start", ""))
        if count is not None:
            upcoming = upcoming[:count]

        from morgen.output import enrich_events

        upcoming = enrich_events(upcoming)
        if response_format == "concise" and not fields:
            fields = EVENT_CONCISE_FIELDS
        morgen_output(upcoming, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=EVENT_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


# ---------------------------------------------------------------------------
# Quick views: today, this-week, this-month
# ---------------------------------------------------------------------------

VIEW_EVENT_CONCISE_FIELDS = ["id", "title", "start", "duration", "participants_display", "location_display"]
VIEW_TASK_CONCISE_FIELDS = ["id", "title", "progress", "due"]


class _MutuallyExclusive(click.Option):
    """Click option that is mutually exclusive with another option."""

    def __init__(self, *args: Any, mutually_exclusive: list[str] | None = None, **kwargs: Any) -> None:
        self._mutually_exclusive = mutually_exclusive or []
        super().__init__(*args, **kwargs)

    def handle_parse_result(self, ctx: click.Context, opts: Mapping[str, Any], args: list[str]) -> Any:
        name = self.name or ""
        for other in self._mutually_exclusive:
            if name in opts and other in opts:
                flag_a = name.replace("_", "-")
                flag_b = other.replace("_", "-")
                msg = f"--{flag_a} and --{flag_b} are mutually exclusive."
                raise click.UsageError(msg)
        return super().handle_parse_result(ctx, opts, args)


def _combined_view(
    start: str,
    end: str,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
    events_only: bool = False,
    tasks_only: bool = False,
    group_name: str | None = None,
    all_calendars: bool = False,
) -> None:
    """Fetch events + tasks and output a categorised view."""

    try:
        client = _get_client()
        cf = _resolve_calendar_filter(group_name, all_calendars)

        result: dict[str, Any] = {}

        if not tasks_only:
            events_data = client.list_all_events(start, end, **_filter_kwargs(cf))
            events_list_raw: list[dict[str, Any]] = list(events_data)
            ctx = click.get_current_context(silent=True)
            if ctx and ctx.params.get("no_frames"):
                events_list_raw = [e for e in events_list_raw if not _is_frame_event(e)]
            events_list_raw.sort(key=lambda x: x.get("start", ""))
            from morgen.output import enrich_events

            events_list_enriched = enrich_events(events_list_raw)
            if response_format == "concise" and not fields:
                from morgen.output import select_fields

                events_list_enriched = select_fields(events_list_enriched, VIEW_EVENT_CONCISE_FIELDS)
            result["events"] = events_list_enriched

        if not events_only:
            tasks_data = client.list_tasks()
            scheduled: list[dict[str, Any]] = []
            overdue: list[dict[str, Any]] = []
            unscheduled: list[dict[str, Any]] = []
            # Compare date portion only (YYYY-MM-DD) to avoid Z vs +00:00 issues
            start_date = start[:10]
            end_date = end[:10]
            for t in tasks_data:
                due = t.get("due", "")
                if due:
                    due_date = due[:10]
                    if start_date <= due_date <= end_date:
                        scheduled.append(t)
                    elif due_date < start_date:
                        overdue.append(t)
                    # Tasks with due > end are outside the range — skip them
                else:
                    unscheduled.append(t)

            task_fields = VIEW_TASK_CONCISE_FIELDS if (response_format == "concise" and not fields) else None
            if task_fields:
                from morgen.output import select_fields

                scheduled = select_fields(scheduled, task_fields)
                overdue = select_fields(overdue, task_fields)
                unscheduled = select_fields(unscheduled, task_fields)

            result["scheduled_tasks"] = scheduled
            result["overdue_tasks"] = overdue
            result["unscheduled_tasks"] = unscheduled

        if fields:
            # Apply field selection to each list in result
            from morgen.output import select_fields

            for key in result:
                if isinstance(result[key], list):
                    result[key] = select_fields(result[key], fields)

        if jq_expr:
            from morgen.output import apply_jq

            result = apply_jq(result, jq_expr)

        if fmt in ("json", "jsonl"):
            morgen_output(result, fmt="json")
        else:
            # For table/csv, render each section separately
            for section, items in result.items():
                if items:
                    click.echo(f"\n## {section.replace('_', ' ').title()}")
                    morgen_output(items, fmt=fmt)

    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


def _view_options(f: Callable[..., Any]) -> Callable[..., Any]:
    """Add --events-only / --tasks-only flags to view commands."""

    @click.option(
        "--events-only",
        is_flag=True,
        default=False,
        cls=_MutuallyExclusive,
        mutually_exclusive=["tasks_only"],
        help="Show only events.",
    )
    @click.option(
        "--tasks-only",
        is_flag=True,
        default=False,
        cls=_MutuallyExclusive,
        mutually_exclusive=["events_only"],
        help="Show only tasks.",
    )
    @functools.wraps(f)
    def wrapper(*args: Any, events_only: bool, tasks_only: bool, **kwargs: Any) -> Any:
        kwargs["events_only"] = events_only
        kwargs["tasks_only"] = tasks_only
        return f(*args, **kwargs)

    return wrapper


@cli.command()
@output_options
@_view_options
@calendar_filter_options
def today(
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
    events_only: bool,
    tasks_only: bool,
    group_name: str | None,
    all_calendars: bool,
) -> None:
    """Combined events + tasks for today."""
    from morgen.time_utils import today_range

    start, end = today_range()
    _combined_view(
        start,
        end,
        fmt,
        fields,
        jq_expr,
        response_format,
        events_only=events_only,
        tasks_only=tasks_only,
        group_name=group_name,
        all_calendars=all_calendars,
    )


@cli.command("this-week")
@output_options
@_view_options
@calendar_filter_options
def this_week(
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
    events_only: bool,
    tasks_only: bool,
    group_name: str | None,
    all_calendars: bool,
) -> None:
    """Combined events + tasks for this week (Mon-Sun)."""
    from morgen.time_utils import this_week_range

    start, end = this_week_range()
    _combined_view(
        start,
        end,
        fmt,
        fields,
        jq_expr,
        response_format,
        events_only=events_only,
        tasks_only=tasks_only,
        group_name=group_name,
        all_calendars=all_calendars,
    )


@cli.command("this-month")
@output_options
@_view_options
@calendar_filter_options
def this_month(
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
    events_only: bool,
    tasks_only: bool,
    group_name: str | None,
    all_calendars: bool,
) -> None:
    """Combined events + tasks for this month."""
    from morgen.time_utils import this_month_range

    start, end = this_month_range()
    _combined_view(
        start,
        end,
        fmt,
        fields,
        jq_expr,
        response_format,
        events_only=events_only,
        tasks_only=tasks_only,
        group_name=group_name,
        all_calendars=all_calendars,
    )


# ---------------------------------------------------------------------------
# groups
# ---------------------------------------------------------------------------


@cli.command()
@output_options
def groups(fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str) -> None:
    """Show configured calendar groups."""
    config = load_morgen_config()
    config_path = _config_file_path()
    result: dict[str, Any] = {
        "config_file": config_path,
        "default_group": config.default_group,
        "active_only": config.active_only,
        "groups": {
            name: {
                "accounts": g.accounts,
                **({"calendars": g.calendars} if g.calendars else {}),
            }
            for name, g in sorted(config.groups.items())
        },
    }
    morgen_output(result, fmt="json", fields=fields, jq_expr=jq_expr)


# ---------------------------------------------------------------------------
# cache management
# ---------------------------------------------------------------------------


@cli.group("cache")
def cache_group() -> None:
    """Manage the local API cache."""


@cache_group.command("clear")
def cache_clear() -> None:
    """Wipe all cached API data."""
    store = _get_cache_store()
    store.clear()
    click.echo(json.dumps({"status": "cleared", "cache_dir": str(store._dir)}))


@cache_group.command("stats")
def cache_stats() -> None:
    """Show cache statistics."""
    store = _get_cache_store()
    click.echo(json.dumps(store.stats(), indent=2, default=str))
