"""CLI entry point for guten-morgen (gm) — Morgen calendar and task management."""

from __future__ import annotations

import functools
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from guten_morgen.cache import CacheStore
    from guten_morgen.client import MorgenClient

import click

from guten_morgen.config import load_settings
from guten_morgen.errors import MorgenError, output_error
from guten_morgen.groups import CalendarFilter, load_morgen_config, resolve_filter
from guten_morgen.markup import markdown_to_html
from guten_morgen.output import render

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
        from guten_morgen.output import truncate_ids

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
    """guten-morgen (gm) — Morgen calendar and task management CLI."""
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

    text = f"""# gm — Calendar & Task Management CLI

## Commands

### Setup
- `gm init [--force]`
  Create config at ~/.config/guten-morgen/config.toml. Prompts for API key.
  --force overwrites an existing file.

### Accounts
- `gm accounts [--json]`
  List connected calendar accounts.

### Calendars
- `gm calendars list [--json]`
  List all calendars across accounts.

- `gm calendars update CALENDAR_ID [--account-id ID] [--name TEXT] [--color HEX] [--busy/--no-busy]`
  Update calendar metadata (name, color, busy status).

### Events
- `gm events list --start ISO --end ISO [--group NAME] [--all-calendars] [--json]`
  List events in a date range. Auto-discovers account/calendar.

- `gm events create --title TEXT --start ISO --duration MINUTES [--calendar-id ID] [--description TEXT] [--meet]`
  Create a new event. --meet auto-attaches a Google Meet link.

- `gm events update ID [--title TEXT] [--start ISO] [--duration MINUTES]`
  `  [--description TEXT] [--series single|future|all]`
  Update an existing event. --series controls recurring event scope.

- `gm events delete ID [--series single|future|all]`
  Delete an event. --series controls recurring event scope.

- `gm events rsvp EVENT_ID --action accept|decline|tentative`
  `  [--comment TEXT] [--notify/--no-notify] [--series single|future|all]`
  `  [--calendar-id ID] [--account-id ID]`
  RSVP to a calendar event. Uses the Morgen sync API.

### Tasks
- `gm tasks list [--limit N] [--status open|completed|all] [--overdue] [--json]`
  `  [--due-before ISO] [--due-after ISO] [--priority N] [--updated-after ISO]`
  `  [--source morgen|linear|notion] [--tag NAME] [--group-by-source] [--list NAME]`
  List tasks from all connected sources. Filters combine with AND logic.
  --source restricts to a single integration. --tag filters by tag name
  (repeatable, OR logic, case-insensitive). --group-by-source returns
  output grouped by source. --updated-after returns only tasks modified
  since the given timestamp. --list filters by task list name (case-insensitive).
  Tasks are enriched with source, source_id, source_url, source_status,
  tag_names, list_name fields. Descriptions are converted from HTML to markdown.

- `gm tasks get ID [--json]`
  Get a single task by ID.

- `gm tasks create --title TEXT [--due ISO] [--priority 0-9] [--description MARKDOWN]`
  `  [--duration MINUTES] [--tag NAME] [--list NAME] [--earliest-start ISO]`
  Create a new task. --duration sets estimatedDuration for AI time-blocking.
  --tag assigns tags by name (repeatable). --list assigns to a task list by name.
  --earliest-start sets the "not before" date. Descriptions accept markdown
  (converted to HTML for the API).

- `gm tasks update ID [--title TEXT] [--due ISO] [--priority 0-9] [--description MARKDOWN]`
  `  [--duration MINUTES] [--tag NAME] [--list NAME] [--earliest-start ISO]`
  Update a task. --duration sets estimatedDuration. --tag replaces tags by name
  (repeatable). --list moves task to a list by name. --earliest-start sets the
  "not before" date. Descriptions accept markdown (converted to HTML for the API).

- `gm tasks schedule ID --start ISO [--duration MINUTES] [--calendar-id ID] [--account-id ID]`
  Schedule a task as a linked calendar event. Fetches the task to derive
  title and duration, creates an event with morgen.so:metadata.taskId.
  Auto-discovers calendar if not specified.

- `gm tasks close ID [--occurrence ISO]`
  Mark a task as completed. --occurrence targets a specific recurring task occurrence.

- `gm tasks reopen ID [--occurrence ISO]`
  Reopen a completed task. --occurrence targets a specific recurring task occurrence.

- `gm tasks move ID [--after TASK_ID] [--parent TASK_ID]`
  Reorder or nest a task.

- `gm tasks delete ID`
  Delete a task.

### Tags
- `gm tags list [--json]`
  List all tags.

- `gm tags get ID [--json]`
  Get a single tag.

- `gm tags create --name TEXT [--color HEX]`
  Create a tag.

- `gm tags update ID [--name TEXT] [--color HEX]`
  Update a tag.

- `gm tags delete ID`
  Delete a tag.

### Lists (Task Lists)
- `gm lists list [--json]`
  List all task lists.

- `gm lists create --name TEXT [--color HEX]`
  Create a task list.

- `gm lists update ID [--name TEXT] [--color HEX]`
  Update a task list.

- `gm lists delete ID`
  Delete a task list.

### Providers
- `gm providers [--json]`
  List available integration providers.

### Availability
- `gm availability --date YYYY-MM-DD [--min-duration MINUTES] [--start HH:MM] [--end HH:MM] [--group NAME]`
  Find available time slots on a given date. Scans events within working hours
  (default 09:00-18:00) and returns gaps >= min-duration (default 30min).
  Output: [{{start, end, duration_minutes}}]

### Quick Views
- `gm today [--json] [--response-format concise] [--events-only] [--tasks-only] [--group NAME]`
  Combined events + tasks for today. Returns categorised output:
  events, scheduled_tasks, overdue_tasks, unscheduled_tasks.

- `gm this-week [--json] [--response-format concise] [--events-only] [--tasks-only] [--group NAME]`
  Combined events + tasks for this week (Mon-Sun). Same categories.

- `gm this-month [--json] [--response-format concise] [--events-only] [--tasks-only] [--group NAME]`
  Combined events + tasks for this month. Same categories.

- `gm next [--count N] [--hours N] [--json] [--response-format concise] [--group NAME]`
  Show next N upcoming events (default: 3, look-ahead: 24h).
  Much cheaper than `today` for "what's next?" queries.

### Calendar Groups
- `gm groups [--json]`
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
- `gm cache clear`
  Wipe all cached API data.

- `gm cache stats`
  Show cache ages, TTLs, and sizes.

## Calendar Groups

Config file: `{config_path}`
Default group: `{config.default_group or "(none)"}`
Active-only: `{config.active_only}`

Configured groups:
{groups_section}

## Recommended Agent Workflow
1. `gm next --json --response-format concise --no-frames`  (what's coming up?)
2. `gm today --json --response-format concise --no-frames` (full daily overview, all sources)
3. `gm tasks list --status open --overdue --json`          (overdue across all sources)
4. `gm tasks create --title "..." --due ... --duration 30` (create with good metadata)
5. `gm tasks schedule <id> --start ISO`                    (time-block a task)
6. `gm tasks close <id>`                                   (complete a task)
7. `gm availability --date YYYY-MM-DD --json`              (find free slots)
8. `gm events rsvp <id> --action accept`                   (respond to invitations)

## Scenarios

### Morning Triage
```
gm today --json --response-format concise --no-frames
gm tasks list --status open --overdue --json --group-by-source
```

### Schedule a Linear Issue
```
gm tasks list --source linear --json
gm tasks schedule <task-id> --start 2026-02-18T14:00:00
```

### Create and Time-Block a Task
```
gm tasks create --title "Write design doc" --due 2026-02-20 --duration 90
gm tasks schedule <task-id> --start 2026-02-18T10:00:00
```

### Cross-Source Task Review
```
gm tasks list --json --group-by-source --response-format concise
```

### Tag-Based Task Lifecycle
Tags model lifecycle stages (create once, reuse forever):
```
gm tags create --name "Active" --color "#22c55e"
gm tags create --name "Waiting-On" --color "#f59e0b"
gm tags create --name "Someday" --color "#6b7280"
```
Assign tags when creating or updating tasks:
```
gm tasks create --title "Review Q1 budget" --tag "Active" --due 2026-02-28
gm tasks update <id> --tag "Waiting-On"
```
Filter by lifecycle stage:
```
gm tasks list --tag "Active" --status open --json
gm tasks list --tag "Waiting-On" --json
gm tasks list --tag "Active" --tag "Waiting-On" --json   # OR: either tag
```

### Find Available Slots & Book Meeting
```
gm availability --date 2026-02-21 --min-duration 30 --json
gm events create --title "1:1 with Pierre" --start 2026-02-21T14:00:00 --duration 30 --meet
```

### RSVP to a Meeting
```
gm events rsvp <event-id> --action accept --comment "On my way"
gm events rsvp <event-id> --action decline --no-notify
```
"""
    click.echo(text)

    # Dynamic task source discovery
    try:
        client = _get_client()
        task_accounts = client.list_task_accounts()
        source_lines = ["  - morgen (native tasks)"]
        for acc in task_accounts:
            name = acc.providerUserDisplayName or ""
            iid = acc.integrationId or ""
            source_lines.append(f"  - {iid} ({name})")
        sources_section = "\n".join(source_lines)
    except Exception:
        sources_section = "  (run `gm accounts` to check connections)"

    click.echo(f"\n## Connected Task Sources\n{sources_section}\n")


def _config_file_path() -> str:
    """Return the resolved config file path for display."""
    from guten_morgen.config import find_config

    found = find_config()
    if found:
        return str(found)
    return "(not found — run `gm init` to create)"


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

_CONFIG_TEMPLATE = """\
# guten-morgen configuration
# Docs: https://github.com/tenfourty/guten-morgen

# API key from https://platform.morgen.so/
api_key = "{api_key}"

# Calendar group filtering (uncomment and customise)
# default_group = "work"
# active_only = true

# [groups.work]
# accounts = ["you@example.com:google"]
# calendars = ["My Calendar"]
"""


def _xdg_config_path() -> Path:
    """Return the XDG config file path for guten-morgen."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        base = Path(xdg)
    else:
        base = Path.home() / ".config"
    return base / "guten-morgen" / "config.toml"


@cli.command()
@click.option("--force", is_flag=True, help="Overwrite existing config file.")
def init(force: bool) -> None:
    """Create a config file at ~/.config/guten-morgen/config.toml."""
    target = _xdg_config_path()

    if target.exists() and not force:
        click.echo(f"Config already exists: {target}")
        click.echo("Use --force to overwrite.")
        raise SystemExit(1)

    api_key = click.prompt(
        "Morgen API key (from https://platform.morgen.so/)",
        hide_input=False,
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_CONFIG_TEMPLATE.format(api_key=api_key))

    click.echo(f"Config written to {target}")
    click.echo("Run `gm events today` to verify.")


def _get_cache_store() -> CacheStore:
    """Return a CacheStore instance (default location)."""
    from guten_morgen.cache import CacheStore

    return CacheStore()


def _get_client(fmt: str = "table") -> MorgenClient:
    """Create a MorgenClient from settings, with cache and retry callback."""
    from guten_morgen.client import MorgenClient
    from guten_morgen.retry import make_agent_retry_callback, make_human_retry_callback

    settings = load_settings()
    ctx = click.get_current_context(silent=True)
    no_cache = ctx.obj.get("no_cache", False) if ctx and ctx.obj else False
    cache = None if no_cache else _get_cache_store()

    on_retry = make_human_retry_callback() if fmt == "table" else make_agent_retry_callback()

    return MorgenClient(settings, cache=cache, on_retry=on_retry)


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
        client = _get_client(fmt)
        data = [a.model_dump(exclude_none=True) for a in client.list_accounts()]
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


@cli.group()
def calendars() -> None:
    """Manage calendars."""


@calendars.command("list")
@output_options
def calendars_list(fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str) -> None:
    """List all calendars across accounts."""
    try:
        client = _get_client(fmt)
        data = [c.model_dump(exclude_none=True) for c in client.list_calendars()]
        if response_format == "concise" and not fields:
            fields = CALENDAR_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=CALENDAR_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@calendars.command("update")
@click.argument("calendar_id")
@click.option("--account-id", default=None, help="Account ID (auto-discovered if omitted).")
@click.option("--name", default=None, help="Override calendar name.")
@click.option("--color", default=None, help="Override calendar color (hex).")
@click.option("--busy/--no-busy", default=None, help="Set calendar busy/free status.")
def calendars_update(
    calendar_id: str,
    account_id: str | None,
    name: str | None,
    color: str | None,
    busy: bool | None,
) -> None:
    """Update calendar metadata (name, color, busy status)."""
    try:
        client = _get_client()
        if not account_id:
            account_id, _ = _auto_discover(client)
        metadata: dict[str, Any] = {}
        if name is not None:
            metadata["overrideName"] = name
        if color is not None:
            metadata["overrideColor"] = color
        if busy is not None:
            metadata["busy"] = busy
        cal_data: dict[str, Any] = {
            "id": calendar_id,
            "accountId": account_id,
            "metadata": metadata,
        }
        result = client.update_calendar(cal_data)
        output = result if result else {"status": "updated", "id": calendar_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
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


def _normalize_due(due: str) -> str:
    """Normalize due date to 19-char ISO 8601 (YYYY-MM-DDTHH:MM:SS).

    The Morgen API requires exactly this format. Accepts:
    - "2026-02-20" -> "2026-02-20T23:59:59"
    - "2026-02-20T23:59:59Z" -> "2026-02-20T23:59:59"
    - "2026-02-20T23:59:59" -> "2026-02-20T23:59:59" (unchanged)
    """
    # Strip trailing Z or timezone offset
    if due.endswith("Z"):
        due = due[:-1]
    elif "+" in due[10:]:
        due = due[: due.index("+", 10)]
    # Date-only: append end-of-day time
    if len(due) == 10:
        due = f"{due}T23:59:59"
    # Truncate to 19 chars if longer
    return due[:19]


def _normalize_earliest_start(val: str) -> str:
    """Normalize earliest start to 19-char ISO 8601 (YYYY-MM-DDTHH:MM:SS).

    Same normalization as _normalize_due but date-only defaults to T00:00:00.
    """
    if val.endswith("Z"):
        val = val[:-1]
    if "+" in val[10:]:
        val = val[: val.index("+", 10)]
    if len(val) == 10:
        val += "T00:00:00"
    return val[:19]


def _resolve_tag_names(client: MorgenClient, names: tuple[str, ...]) -> list[str]:
    """Resolve tag names to IDs. Case-insensitive matching."""
    all_tags = client.list_tags()
    name_to_id = {t.name.lower(): t.id for t in all_tags}
    return [name_to_id[n.lower()] for n in names if n.lower() in name_to_id]


def _resolve_list_name(client: MorgenClient, name: str) -> str:
    """Resolve a task list name to its ID. Case-insensitive matching."""
    all_lists = client.list_task_lists()
    name_to_id = {tl.name.lower(): tl.id for tl in all_lists}
    lid = name_to_id.get(name.lower())
    if lid is None:
        available = ", ".join(tl.name for tl in all_lists)
        msg = f"Task list '{name}' not found. Available: {available}"
        raise click.ClickException(msg)
    return lid


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
    calendar_accounts = [a for a in accounts_data if "calendars" in a.integrationGroups]
    account = calendar_accounts[0] if calendar_accounts else accounts_data[0]
    account_id = account.id

    calendars_data = client.list_calendars()
    # Filter to calendars belonging to this account
    account_cals = [c for c in calendars_data if c.accountId == account_id]
    # Prefer writable calendars (myRights is a dict with mayWriteAll, mayWriteOwn, etc.)
    writable = [c.id for c in account_cals if _is_writable(c.model_dump())]
    if not writable:
        # Fall back to all calendars for the account
        writable = [c.id for c in account_cals]
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
        client = _get_client(fmt)
        if account_id and calendar_ids_str:
            cal_ids = [s.strip() for s in calendar_ids_str.split(",")]
            data_models = client.list_events(account_id, cal_ids, start, end)
        else:
            cf = _resolve_calendar_filter(group_name, all_calendars)
            data_models = client.list_all_events(start, end, **_filter_kwargs(cf))
        data = [e.model_dump(by_alias=True) for e in data_models]
        ctx = click.get_current_context(silent=True)
        if ctx and ctx.params.get("no_frames"):
            data = [e for e in data if not _is_frame_event(e)]
        from guten_morgen.output import enrich_events

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
@click.option("--meet", is_flag=True, default=False, help="Auto-attach a Google Meet link.")
def events_create(
    title: str,
    start: str,
    duration: int,
    calendar_id: str | None,
    account_id: str | None,
    description: str | None,
    timezone: str | None,
    meet: bool,
) -> None:
    """Create a new event."""
    try:
        client = _get_client()
        if not account_id or not calendar_id:
            account_id, cal_ids = _auto_discover(client)
            calendar_id = calendar_id or cal_ids[0]
        if not timezone:
            from guten_morgen.time_utils import get_local_timezone

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
        if meet:
            event_data["morgen.so:requestVirtualRoom"] = "default"
        result = client.create_event(event_data)
        output = result.model_dump(by_alias=True, exclude_none=True) if result else {"status": "created"}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
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
@click.option(
    "--series",
    "series_mode",
    type=click.Choice(["single", "future", "all"]),
    default=None,
    help="Series update mode for recurring events.",
)
def events_update(
    event_id: str,
    title: str | None,
    start: str | None,
    duration: int | None,
    description: str | None,
    calendar_id: str | None,
    account_id: str | None,
    series_mode: str | None,
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
        result = client.update_event(event_data, series_update_mode=series_mode)
        if result:
            output = result.model_dump(by_alias=True, exclude_none=True)
        else:
            output = {"status": "updated", "id": event_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@events.command("delete")
@click.argument("event_id")
@click.option("--calendar-id", default=None, help="Calendar ID.")
@click.option("--account-id", default=None, help="Account ID.")
@click.option(
    "--series",
    "series_mode",
    type=click.Choice(["single", "future", "all"]),
    default=None,
    help="Series update mode for recurring events.",
)
def events_delete(event_id: str, calendar_id: str | None, account_id: str | None, series_mode: str | None) -> None:
    """Delete an event."""
    try:
        client = _get_client()
        if not account_id or not calendar_id:
            account_id, cal_ids = _auto_discover(client)
            calendar_id = calendar_id or cal_ids[0]
        client.delete_event(
            {"id": event_id, "calendarId": calendar_id, "accountId": account_id},
            series_update_mode=series_mode,
        )
        click.echo(json.dumps({"status": "deleted", "id": event_id}))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@events.command("rsvp")
@click.argument("event_id")
@click.option(
    "--action",
    required=True,
    type=click.Choice(["accept", "decline", "tentative"]),
    help="RSVP action.",
)
@click.option("--comment", default=None, help="Optional comment to organizer.")
@click.option("--notify/--no-notify", default=True, help="Notify the organizer (default: yes).")
@click.option(
    "--series",
    "series_mode",
    type=click.Choice(["single", "future", "all"]),
    default=None,
    help="Series update mode for recurring events.",
)
@click.option("--calendar-id", default=None, help="Calendar ID (auto-discovered if omitted).")
@click.option("--account-id", default=None, help="Account ID (auto-discovered if omitted).")
def events_rsvp(
    event_id: str,
    action: str,
    comment: str | None,
    notify: bool,
    series_mode: str | None,
    calendar_id: str | None,
    account_id: str | None,
) -> None:
    """RSVP to a calendar event (accept, decline, tentative)."""
    try:
        client = _get_client()
        if not account_id or not calendar_id:
            account_id, cal_ids = _auto_discover(client)
            calendar_id = calendar_id or cal_ids[0]
        result = client.rsvp_event(
            action=action,
            event_id=event_id,
            calendar_id=calendar_id,
            account_id=account_id,
            notify_organizer=notify,
            comment=comment,
            series_update_mode=series_mode,
        )
        click.echo(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------

AVAILABILITY_COLUMNS = ["start", "end", "duration_minutes"]


@cli.command()
@click.option("--date", required=True, help="Date to check (YYYY-MM-DD).")
@click.option("--min-duration", default=30, type=int, help="Minimum slot duration in minutes (default: 30).")
@click.option("--start", "window_start", default="09:00", help="Working hours start (HH:MM, default: 09:00).")
@click.option("--end", "window_end", default="18:00", help="Working hours end (HH:MM, default: 18:00).")
@output_options
@calendar_filter_options
def availability(
    date: str,
    min_duration: int,
    window_start: str,
    window_end: str,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
    group_name: str | None,
    all_calendars: bool,
) -> None:
    """Find available time slots on a given date."""
    try:
        client = _get_client(fmt)
        cf = _resolve_calendar_filter(group_name, all_calendars)

        day_start = f"{date}T00:00:00"
        day_end = f"{date}T23:59:59"
        events_models = client.list_all_events(day_start, day_end, **_filter_kwargs(cf))
        events_data = [e.model_dump(by_alias=True) for e in events_models]

        from guten_morgen.time_utils import compute_free_slots

        slots = compute_free_slots(
            events=events_data,
            day=date,
            window_start=window_start,
            window_end=window_end,
            min_duration_minutes=min_duration,
        )
        morgen_output(slots, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=AVAILABILITY_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


# ---------------------------------------------------------------------------
# tasks
# ---------------------------------------------------------------------------

TASK_COLUMNS = [
    "id",
    "title",
    "progress",
    "priority",
    "due",
    "list_name",
    "tag_names",
    "source",
    "source_id",
    "source_status",
]
TASK_CONCISE_FIELDS = ["id", "title", "progress", "due", "list_name", "tag_names", "source"]


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
@click.option("--source", default=None, help="Filter by task source (morgen, linear, notion, etc.).")
@click.option("--tag", "tag_names", multiple=True, help="Filter by tag name (repeatable, OR logic).")
@click.option("--list", "list_name", default=None, help="Filter by task list name.")
@click.option("--group-by-source", is_flag=True, default=False, help="Group output by task source.")
@click.option("--updated-after", default=None, help="Only tasks updated after this datetime (ISO 8601).")
@output_options
def tasks_list(
    limit: int,
    status_filter: str,
    due_before: str | None,
    due_after: str | None,
    overdue: bool,
    priority_filter: int | None,
    source: str | None,
    tag_names: tuple[str, ...],
    list_name: str | None,
    group_by_source: bool,
    updated_after: str | None,
    fmt: str,
    fields: list[str] | None,
    jq_expr: str | None,
    response_format: str,
) -> None:
    """List tasks."""
    try:
        client = _get_client(fmt)
        result = client.list_all_tasks(source=source, limit=limit, updated_after=updated_after)
        data = [t.model_dump() for t in result.tasks]
        label_defs = [ld.model_dump() for ld in result.labelDefs]

        # Fetch tags for enrichment and filtering (cached)
        all_tags = [t.model_dump() for t in client.list_tags()]
        all_task_lists = [tl.model_dump() for tl in client.list_task_lists()]

        # Resolve tag name filter to IDs (OR logic: match any)
        tag_id_filter: set[str] = set()
        if tag_names:
            name_to_id = {t["name"].lower(): t["id"] for t in all_tags}
            for tn in tag_names:
                tid = name_to_id.get(tn.lower())
                if tid:
                    tag_id_filter.add(tid)

        # Resolve list name filter to ID
        list_id_filter: str | None = None
        if list_name:
            list_id_filter = _resolve_list_name(client, list_name)

        # Enrich tasks with normalized source metadata + tag names + list_name
        from guten_morgen.output import enrich_tasks

        data = enrich_tasks(data, label_defs=label_defs, tags=all_tags, task_lists=all_task_lists)

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

            # Tag filter (OR logic: task must have at least one matching tag)
            if tag_id_filter:
                task_tags = set(t.get("tags", []))
                if not task_tags & tag_id_filter:
                    continue

            # List filter
            if list_id_filter and t.get("taskListId") != list_id_filter:
                continue

            filtered.append(t)

        if response_format == "concise" and not fields:
            fields = TASK_CONCISE_FIELDS

        # Group by source if requested
        if group_by_source:
            grouped: dict[str, list[dict[str, Any]]] = {}
            for t in filtered:
                src = t.get("source", "morgen")
                grouped.setdefault(src, []).append(t)

            # Apply field selection per-group (not on the grouped dict itself)
            if fields:
                from guten_morgen.output import select_fields

                grouped = {k: select_fields(v, fields) for k, v in grouped.items()}

            if fmt in ("json", "jsonl"):
                morgen_output(grouped, fmt="json", jq_expr=jq_expr)
            else:
                for section, items in grouped.items():
                    if items:
                        click.echo(f"\n## {section}")
                        morgen_output(items, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=TASK_COLUMNS)
        else:
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
        client = _get_client(fmt)
        data = client.get_task(task_id).model_dump()
        if response_format == "concise" and not fields:
            fields = TASK_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("create")
@click.option("--title", required=True, help="Task title.")
@click.option("--due", default=None, help="Due datetime (ISO 8601).")
@click.option("--priority", default=None, type=int, help="Priority (0-9).")
@click.option("--description", default=None, help="Task description.")
@click.option("--duration", default=None, type=int, help="Estimated duration in minutes.")
@click.option("--tag", "tag_names", multiple=True, help="Tag name (repeatable). Resolved to IDs.")
@click.option("--list", "list_name", default=None, help="Task list name. Resolved to ID.")
@click.option("--earliest-start", default=None, help="Earliest start datetime (ISO 8601).")
def tasks_create(
    title: str,
    due: str | None,
    priority: int | None,
    description: str | None,
    duration: int | None,
    tag_names: tuple[str, ...],
    list_name: str | None,
    earliest_start: str | None,
) -> None:
    """Create a new task."""
    try:
        client = _get_client()
        task_data: dict[str, Any] = {"title": title}
        if due:
            task_data["due"] = _normalize_due(due)
        if priority is not None:
            task_data["priority"] = priority
        if description:
            task_data["description"] = markdown_to_html(description) or description
        if duration is not None:
            task_data["estimatedDuration"] = f"PT{duration}M"
        if tag_names:
            task_data["tags"] = _resolve_tag_names(client, tag_names)
        if list_name:
            task_data["taskListId"] = _resolve_list_name(client, list_name)
        if earliest_start:
            task_data["earliestStart"] = _normalize_earliest_start(earliest_start)
        result = client.create_task(task_data)
        output = result.model_dump(exclude_none=True) if result else {"status": "created"}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("update")
@click.argument("task_id")
@click.option("--title", default=None, help="New title.")
@click.option("--due", default=None, help="New due datetime (ISO 8601).")
@click.option("--priority", default=None, type=int, help="New priority (0-9).")
@click.option("--description", default=None, help="New description.")
@click.option("--duration", default=None, type=int, help="Estimated duration in minutes.")
@click.option("--tag", "tag_names", multiple=True, help="Tag name (repeatable). Replaces existing tags.")
@click.option("--list", "list_name", default=None, help="Task list name. Resolved to ID.")
@click.option("--earliest-start", default=None, help="Earliest start datetime (ISO 8601).")
def tasks_update(
    task_id: str,
    title: str | None,
    due: str | None,
    priority: int | None,
    description: str | None,
    duration: int | None,
    tag_names: tuple[str, ...],
    list_name: str | None,
    earliest_start: str | None,
) -> None:
    """Update a task."""
    try:
        client = _get_client()
        task_data: dict[str, Any] = {"id": task_id}
        if title is not None:
            task_data["title"] = title
        if due is not None:
            task_data["due"] = _normalize_due(due)
        if priority is not None:
            task_data["priority"] = priority
        if description is not None:
            task_data["description"] = markdown_to_html(description) or description
        if duration is not None:
            task_data["estimatedDuration"] = f"PT{duration}M"
        if tag_names:
            task_data["tags"] = _resolve_tag_names(client, tag_names)
        if list_name:
            task_data["taskListId"] = _resolve_list_name(client, list_name)
        if earliest_start:
            task_data["earliestStart"] = _normalize_earliest_start(earliest_start)
        result = client.update_task(task_data)
        output = result.model_dump(exclude_none=True) if result else {"status": "updated", "id": task_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("close")
@click.argument("task_id")
@click.option("--occurrence", default=None, help="Occurrence start (ISO 8601) for recurring tasks.")
def tasks_close(task_id: str, occurrence: str | None) -> None:
    """Mark a task as completed."""
    try:
        client = _get_client()
        result = client.close_task(task_id, occurrence_start=occurrence)
        output = result.model_dump(exclude_none=True) if result else {"status": "closed", "id": task_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("reopen")
@click.argument("task_id")
@click.option("--occurrence", default=None, help="Occurrence start (ISO 8601) for recurring tasks.")
def tasks_reopen(task_id: str, occurrence: str | None) -> None:
    """Reopen a completed task."""
    try:
        client = _get_client()
        result = client.reopen_task(task_id, occurrence_start=occurrence)
        output = result.model_dump(exclude_none=True) if result else {"status": "reopened", "id": task_id}
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
        output = result.model_dump(exclude_none=True) if result else {"status": "moved", "id": task_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@tasks.command("schedule")
@click.argument("task_id")
@click.option("--start", required=True, help="Start datetime (ISO 8601).")
@click.option("--duration", default=None, type=int, help="Duration in minutes (overrides task's estimatedDuration).")
@click.option("--calendar-id", default=None, help="Calendar ID (auto-discovered if omitted).")
@click.option("--account-id", default=None, help="Account ID (auto-discovered if omitted).")
@click.option("--timezone", default=None, help="Time zone (e.g. Europe/Paris). Defaults to system timezone.")
def tasks_schedule(
    task_id: str,
    start: str,
    duration: int | None,
    calendar_id: str | None,
    account_id: str | None,
    timezone: str | None,
) -> None:
    """Schedule a task as a linked calendar event."""
    try:
        client = _get_client()
        if not account_id or not calendar_id:
            account_id, cal_ids = _auto_discover(client)
            calendar_id = calendar_id or cal_ids[0]
        result = client.schedule_task(
            task_id=task_id,
            start=start,
            calendar_id=calendar_id,
            account_id=account_id,
            duration_minutes=duration,
            timezone=timezone,
        )
        output = result.model_dump(by_alias=True, exclude_none=True) if result else {"status": "scheduled"}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
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
        client = _get_client(fmt)
        data = [t.model_dump() for t in client.list_tags()]
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
        client = _get_client(fmt)
        data = client.get_tag(tag_id).model_dump()
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
        output = result.model_dump(exclude_none=True) if result else {"status": "created"}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
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
        output = result.model_dump(exclude_none=True) if result else {"status": "updated", "id": tag_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
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
# lists (task lists)
# ---------------------------------------------------------------------------

LIST_COLUMNS = ["id", "name", "color", "role"]
LIST_CONCISE_FIELDS = ["id", "name", "color"]


@cli.group()
def lists() -> None:
    """Manage task lists."""


@lists.command("list")
@output_options
def lists_list(fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str) -> None:
    """List all task lists."""
    try:
        client = _get_client(fmt)
        data = [tl.model_dump() for tl in client.list_task_lists()]
        if response_format == "concise" and not fields:
            fields = LIST_CONCISE_FIELDS
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=LIST_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@lists.command("create")
@click.option("--name", required=True, help="List name.")
@click.option("--color", default=None, help="List color (hex).")
def lists_create(name: str, color: str | None) -> None:
    """Create a task list."""
    try:
        client = _get_client()
        list_data: dict[str, Any] = {"name": name}
        if color:
            list_data["color"] = color
        result = client.create_task_list(list_data)
        output = result.model_dump(exclude_none=True) if result else {"status": "created"}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@lists.command("update")
@click.argument("list_id")
@click.option("--name", default=None, help="New list name.")
@click.option("--color", default=None, help="New list color (hex).")
def lists_update(list_id: str, name: str | None, color: str | None) -> None:
    """Update a task list."""
    try:
        client = _get_client()
        list_data: dict[str, Any] = {"id": list_id}
        if name is not None:
            list_data["name"] = name
        if color is not None:
            list_data["color"] = color
        result = client.update_task_list(list_data)
        output = result.model_dump(exclude_none=True) if result else {"status": "updated", "id": list_id}
        click.echo(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


@lists.command("delete")
@click.argument("list_id")
def lists_delete(list_id: str) -> None:
    """Delete a task list."""
    try:
        client = _get_client()
        client.delete_task_list(list_id)
        click.echo(json.dumps({"status": "deleted", "id": list_id}))
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------

PROVIDER_COLUMNS = ["id", "name", "type"]


@cli.command()
@output_options
def providers(fmt: str, fields: list[str] | None, jq_expr: str | None, response_format: str) -> None:
    """List available integration providers."""
    try:
        client = _get_client(fmt)
        data = client.list_providers()
        morgen_output(data, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=PROVIDER_COLUMNS)
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
    from guten_morgen.time_utils import end_of_next_day

    try:
        client = _get_client(fmt)
        cf = _resolve_calendar_filter(group_name, all_calendars)

        now = _now_utc()
        end = end_of_next_day(now)

        events_data = client.list_all_events(now.isoformat(), end, **_filter_kwargs(cf))

        # Filter to events starting after now — use attribute access on Event models
        upcoming = [e for e in events_data if (e.start or "") >= now.isoformat()[:19]]
        # Convert to dicts for _is_frame_event and downstream processing
        upcoming_dicts = [e.model_dump(by_alias=True) for e in upcoming]
        ctx = click.get_current_context(silent=True)
        if ctx and ctx.params.get("no_frames"):
            upcoming_dicts = [e for e in upcoming_dicts if not _is_frame_event(e)]
        upcoming_dicts.sort(key=lambda x: x.get("start", ""))
        if count is not None:
            upcoming_dicts = upcoming_dicts[:count]

        from guten_morgen.output import enrich_events

        upcoming_dicts = enrich_events(upcoming_dicts)
        if response_format == "concise" and not fields:
            fields = EVENT_CONCISE_FIELDS
        morgen_output(upcoming_dicts, fmt=fmt, fields=fields, jq_expr=jq_expr, columns=EVENT_COLUMNS)
    except MorgenError as e:
        output_error(e.error_type, str(e), e.suggestions)


# ---------------------------------------------------------------------------
# Quick views: today, this-week, this-month
# ---------------------------------------------------------------------------

VIEW_EVENT_CONCISE_FIELDS = ["id", "title", "start", "duration", "participants_display", "location_display"]
VIEW_TASK_CONCISE_FIELDS = ["id", "title", "progress", "due", "source"]


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
        client = _get_client(fmt)
        cf = _resolve_calendar_filter(group_name, all_calendars)

        result: dict[str, Any] = {}

        if not tasks_only:
            events_models = client.list_all_events(start, end, **_filter_kwargs(cf))
            events_list_raw: list[dict[str, Any]] = [e.model_dump(by_alias=True) for e in events_models]
            ctx = click.get_current_context(silent=True)
            if ctx and ctx.params.get("no_frames"):
                events_list_raw = [e for e in events_list_raw if not _is_frame_event(e)]
            events_list_raw.sort(key=lambda x: x.get("start", ""))
            from guten_morgen.output import enrich_events

            events_list_enriched = enrich_events(events_list_raw)
            if response_format == "concise" and not fields:
                from guten_morgen.output import select_fields

                events_list_enriched = select_fields(events_list_enriched, VIEW_EVENT_CONCISE_FIELDS)
            result["events"] = events_list_enriched

        if not events_only:
            tasks_result = client.list_all_tasks()
            from guten_morgen.output import enrich_tasks

            all_tags = [t.model_dump() for t in client.list_tags()]
            all_task_lists = [tl.model_dump() for tl in client.list_task_lists()]
            tasks_data = enrich_tasks(
                [t.model_dump() for t in tasks_result.tasks],
                label_defs=[ld.model_dump() for ld in tasks_result.labelDefs],
                tags=all_tags,
                task_lists=all_task_lists,
            )
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
                from guten_morgen.output import select_fields

                scheduled = select_fields(scheduled, task_fields)
                overdue = select_fields(overdue, task_fields)
                unscheduled = select_fields(unscheduled, task_fields)

            result["scheduled_tasks"] = scheduled
            result["overdue_tasks"] = overdue
            result["unscheduled_tasks"] = unscheduled

        if fields:
            # Apply field selection to each list in result
            from guten_morgen.output import select_fields

            for key in result:
                if isinstance(result[key], list):
                    result[key] = select_fields(result[key], fields)

        if jq_expr:
            from guten_morgen.output import apply_jq

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
    from guten_morgen.time_utils import today_range

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
    from guten_morgen.time_utils import this_week_range

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
    from guten_morgen.time_utils import this_month_range

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
