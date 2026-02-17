"""CLI entry point for morgen — Morgen calendar and task management."""

from __future__ import annotations

import functools
from typing import Any

import click

from morgen.output import render

# ---------------------------------------------------------------------------
# Shared output options decorator
# ---------------------------------------------------------------------------


def output_options(f):  # type: ignore[no-untyped-def]
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
