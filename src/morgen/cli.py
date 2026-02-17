"""CLI entry point for morgen — Morgen calendar and task management."""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from morgen.client import MorgenClient

import click

from morgen.config import load_settings
from morgen.errors import MorgenError, output_error
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
    @functools.wraps(f)
    def wrapper(
        *args: Any,
        fmt: str,
        json_flag: bool,
        fields_str: str | None,
        jq_expr: str | None,
        response_format: str,
        **kwargs: Any,
    ) -> Any:
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
    """Render data to stdout."""
    text = render(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=columns)
    click.echo(text)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """Morgen CLI — calendar and task management for Control Tower."""


# ---------------------------------------------------------------------------
# usage
# ---------------------------------------------------------------------------


@cli.command()
def usage() -> None:
    """Self-documentation for AI agents."""
    text = """# morgen — Calendar & Task Management CLI

## Commands

### Accounts & Calendars
- `morgen accounts [--json]`
  List connected calendar accounts.

- `morgen calendars [--json]`
  List all calendars across accounts.

### Events
- `morgen events list --start ISO --end ISO [--json]`
  List events in a date range. Auto-discovers account/calendar.

- `morgen events create --title TEXT --start ISO --duration MINUTES [--calendar-id ID] [--description TEXT]`
  Create a new event.

- `morgen events update ID [--title TEXT] [--start ISO] [--duration MINUTES] [--description TEXT]`
  Update an existing event.

- `morgen events delete ID`
  Delete an event.

### Tasks
- `morgen tasks list [--limit N] [--json]`
  List tasks.

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
- `morgen today [--json] [--response-format concise]`
  Combined events + tasks for today.

- `morgen this-week [--json] [--response-format concise]`
  Combined events + tasks for this week (Mon-Sun).

- `morgen this-month [--json] [--response-format concise]`
  Combined events + tasks for this month.

## Global Options
- `--format table|json|jsonl|csv` (default: table)
- `--json` (shortcut for --format json)
- `--fields <comma-separated>` (select specific fields)
- `--jq <expression>` (jq filtering)
- `--response-format detailed|concise` (concise uses ~1/3 tokens)

## Recommended Workflow
1. `morgen today --json --response-format concise`     (daily overview)
2. `morgen events list --start ... --end ... --json`   (date range query)
3. `morgen tasks create --title "..." --due ...`       (create task)
4. `morgen tasks close <id>`                           (complete task)
"""
    click.echo(text)


def _get_client() -> MorgenClient:
    """Create a MorgenClient from settings."""
    from morgen.client import MorgenClient

    settings = load_settings()
    return MorgenClient(settings)


# ---------------------------------------------------------------------------
# accounts
# ---------------------------------------------------------------------------

ACCOUNT_COLUMNS = ["accountId", "name", "email", "providerId"]
ACCOUNT_CONCISE_FIELDS = ["accountId", "name"]


@cli.command()
@output_options
def accounts(
    fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str
) -> None:
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

CALENDAR_COLUMNS = ["calendarId", "accountId", "name", "color", "writable"]
CALENDAR_CONCISE_FIELDS = ["calendarId", "name", "writable"]


@cli.command()
@output_options
def calendars(
    fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str
) -> None:
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

EVENT_COLUMNS = ["id", "title", "start", "end", "calendarId"]
EVENT_CONCISE_FIELDS = ["id", "title", "start", "end"]


@cli.group()
def events() -> None:
    """Manage calendar events."""


def _auto_discover(client: MorgenClient) -> tuple[str, list[str]]:
    """Auto-discover first account and its writable calendars."""
    accounts_data = client.list_accounts()
    if not accounts_data:
        raise MorgenError("No connected accounts found", suggestions=["Connect an account in Morgen"])
    account_id: str = accounts_data[0]["accountId"]

    calendars_data = client.list_calendars()
    writable = [c["calendarId"] for c in calendars_data if c.get("writable") and c.get("accountId") == account_id]
    if not writable:
        writable = [c["calendarId"] for c in calendars_data if c.get("accountId") == account_id]
    if not writable:
        raise MorgenError("No calendars found for account", suggestions=["Check calendar sync in Morgen"])
    return account_id, writable


@events.command("list")
@click.option("--start", required=True, help="Start datetime (ISO 8601).")
@click.option("--end", required=True, help="End datetime (ISO 8601).")
@click.option("--account-id", default=None, help="Account ID (auto-discovered if omitted).")
@click.option("--calendar-id", "calendar_ids_str", default=None, help="Comma-separated calendar IDs.")
@output_options
def events_list(
    start: str,
    end: str,
    account_id: str | None,
    calendar_ids_str: str | None,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
) -> None:
    """List events in a date range."""
    try:
        client = _get_client()
        if account_id and calendar_ids_str:
            cal_ids = [s.strip() for s in calendar_ids_str.split(",")]
        else:
            account_id, cal_ids = _auto_discover(client)
        data = client.list_events(account_id, cal_ids, start, end)
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
def events_create(
    title: str,
    start: str,
    duration: int,
    calendar_id: str | None,
    account_id: str | None,
    description: str | None,
) -> None:
    """Create a new event."""
    try:
        client = _get_client()
        if not account_id or not calendar_id:
            account_id, cal_ids = _auto_discover(client)
            calendar_id = calendar_id or cal_ids[0]
        event_data: dict[str, Any] = {
            "title": title,
            "start": start,
            "duration": f"PT{duration}M",
            "calendarId": calendar_id,
            "accountId": account_id,
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
        click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))
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

TASK_COLUMNS = ["id", "title", "status", "priority", "due"]
TASK_CONCISE_FIELDS = ["id", "title", "status", "due"]


@cli.group()
def tasks() -> None:
    """Manage tasks."""


@tasks.command("list")
@click.option("--limit", default=100, type=int, help="Max number of tasks to return.")
@output_options
def tasks_list(
    limit: int,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
) -> None:
    """List tasks."""
    try:
        client = _get_client()
        data = client.list_tasks(limit=limit)
        if response_format == "concise" and not fields:
            fields = TASK_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=TASK_COLUMNS)
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
        click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("close")
@click.argument("task_id")
def tasks_close(task_id: str) -> None:
    """Mark a task as completed."""
    try:
        client = _get_client()
        result = client.close_task(task_id)
        click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("reopen")
@click.argument("task_id")
def tasks_reopen(task_id: str) -> None:
    """Reopen a completed task."""
    try:
        client = _get_client()
        result = client.reopen_task(task_id)
        click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))
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
        click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))
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
def tags_list(
    fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str
) -> None:
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
        click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))
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
# Quick views: today, this-week, this-month
# ---------------------------------------------------------------------------

VIEW_CONCISE_FIELDS = ["type", "id", "title", "start", "status"]


def _combined_view(
    start: str,
    end: str,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
) -> None:
    """Fetch events + tasks and output a combined timeline."""

    try:
        client = _get_client()
        account_id, cal_ids = _auto_discover(client)

        events_data = client.list_events(account_id, cal_ids, start, end)
        tasks_data = client.list_tasks()

        # Tag each item with type
        timeline: list[dict[str, Any]] = []
        for e in events_data:
            timeline.append({"type": "event", **e})
        for t in tasks_data:
            due = t.get("due", "")
            if due and start <= due <= end:
                timeline.append({"type": "task", **t})
            elif not due:
                # Include tasks without due date
                timeline.append({"type": "task", **t})

        # Sort: events by start, tasks at end
        timeline.sort(key=lambda x: x.get("start", x.get("due", "9999")))

        if response_format == "concise" and not fields:
            fields = VIEW_CONCISE_FIELDS

        morgen_output(timeline, fmt=fmt, fields=fields, jq_expr=jq_expr)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@cli.command()
@output_options
def today(
    fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str
) -> None:
    """Combined events + tasks for today."""
    from morgen.time_utils import today_range

    start, end = today_range()
    _combined_view(start, end, fmt, fields, jq_expr, response_format)


@cli.command("this-week")
@output_options
def this_week(
    fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str
) -> None:
    """Combined events + tasks for this week (Mon-Sun)."""
    from morgen.time_utils import this_week_range

    start, end = this_week_range()
    _combined_view(start, end, fmt, fields, jq_expr, response_format)


@cli.command("this-month")
@output_options
def this_month(
    fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str
) -> None:
    """Combined events + tasks for this month."""
    from morgen.time_utils import this_month_range

    start, end = this_month_range()
    _combined_view(start, end, fmt, fields, jq_expr, response_format)
