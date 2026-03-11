# MCP Server

MCP (Model Context Protocol) server for guten-morgen — exposes calendar and task management tools to AI agents via stdio transport.

## Install

```bash
pip install "guten-morgen[mcp]"
```

Depends on `mcp>=1.2` (FastMCP).

## Usage

```bash
gm-mcp
# or
gm mcp
```

Starts the MCP server on stdio transport. Configure your AI tool to connect to this process.

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "guten-morgen": {
      "command": "/Users/YOU/.local/bin/gm-mcp",
      "args": []
    }
  }
}
```

> **Important:** Use the full path to the `gm-mcp` binary. Claude Desktop launches with a minimal PATH that does not include `~/.local/bin/`. Find the path with `which gm-mcp`.

### Claude Code

`.claude/settings.local.json`:

```json
{
  "mcpServers": {
    "guten-morgen": {
      "command": "gm-mcp",
      "args": [],
      "type": "stdio"
    }
  }
}
```

Claude Code inherits your shell PATH, so the short name works here.

## Available Tools

### Read-only (12 tools)

| Tool | Description |
|------|-------------|
| `gm_today` | Today's events and tasks — daily snapshot. Events, scheduled/overdue/unscheduled tasks with capping. |
| `gm_next` | Next upcoming events — lightweight alternative to `gm_today`. |
| `gm_this_week` | This week's events and tasks (Mon–Sun) — for weekly planning. |
| `gm_this_month` | This month's events and tasks — for monthly planning and review. |
| `gm_events_list` | List events in a date range (ISO 8601 start/end). |
| `gm_availability` | Find available time slots on a given date. |
| `gm_tasks_list` | List tasks with filtering by status, tag, list, project, source. |
| `gm_tasks_get` | Get a single task by ID — full detail view including description. |
| `gm_lists` | List task lists (areas of focus) — id, name, colour. |
| `gm_tags` | List tags (lifecycle status) — id, name, colour. |
| `gm_accounts` | List connected calendar accounts — id, name, email, integration type. |
| `gm_groups` | List configured calendar groups — shows valid group names for filtering. |

### Event mutations (4 tools)

| Tool | Description |
|------|-------------|
| `gm_events_create` | Create a new calendar event. Calendar auto-discovered. |
| `gm_events_update` | Update an existing event. Only provided fields are modified. |
| `gm_events_delete` | Delete a calendar event. Supports series mode for recurring events. |
| `gm_events_rsvp` | RSVP to a calendar event (accept, decline, tentative). |

### Task mutations (7 tools)

| Tool | Description |
|------|-------------|
| `gm_tasks_create` | Create a new task with optional due date, tag, list, project, ref. |
| `gm_tasks_update` | Update an existing task. Supports surgical project/ref replacement. |
| `gm_tasks_close` | Mark a task as completed. |
| `gm_tasks_reopen` | Reopen a completed task. |
| `gm_tasks_delete` | Delete a task permanently. |
| `gm_tasks_move` | Reorder or nest a task (after/parent). |
| `gm_tasks_schedule` | Schedule a task as a linked calendar event (timeblocking). |

### Tag/list CRUD (6 tools)

| Tool | Description |
|------|-------------|
| `gm_tags_create` | Create a new tag (lifecycle status label). |
| `gm_tags_update` | Update a tag's name or colour. |
| `gm_tags_delete` | Delete a tag permanently. |
| `gm_lists_create` | Create a new task list (area of focus). |
| `gm_lists_update` | Update a task list's name or colour. |
| `gm_lists_delete` | Delete a task list permanently. |

## Resources

| URI | Description |
|-----|-------------|
| `gm://lists` | Task lists (areas of focus) — id, name, colour |
| `gm://tags` | Tags (lifecycle status) — id, name, colour |
| `gm://groups` | Calendar groups — configured group names and their accounts |

## Tool Parameters

### `gm_today`

```
group: str | None       # calendar group name (None = all)
events_only: bool       # skip tasks
tasks_only: bool        # skip events
max_unscheduled: int    # cap unscheduled tasks (default 20)
```

### `gm_next`

```
count: int = 3          # max events to return
```

### `gm_this_week` / `gm_this_month`

```
group: str | None       # calendar group name
events_only: bool       # skip tasks
tasks_only: bool        # skip events
max_unscheduled: int    # cap unscheduled tasks (default 20)
```

### `gm_events_list`

```
start: str              # ISO 8601 start datetime (required)
end: str                # ISO 8601 end datetime (required)
group: str | None       # calendar group name
```

### `gm_availability`

```
date: str               # YYYY-MM-DD (required)
min_duration_minutes: int  # minimum slot duration (default 30)
start_hour: str | None  # working hours start (default "08:00")
end_hour: str | None    # working hours end (default "18:00")
group: str | None       # calendar group name
```

### `gm_tasks_list`

```
status: str = "open"    # "open", "completed", or "all"
overdue: bool           # only overdue tasks
source: str | None      # filter by source (morgen, linear, etc.)
tag: str | None         # filter by tag name (comma-separated)
list_name: str | None   # filter by list name
project: str | None     # filter by project name (substring match)
limit: int = 25         # max results (1-100)
```

> **Note:** `status="completed"` only returns tasks from local cache. The Morgen API requires `updatedAfter` to return completed tasks — use `gm` CLI with `--status completed --since` for comprehensive results.

### `gm_tasks_get`

```
task_id: str            # task ID (required)
```

### `gm_tasks_create`

```
title: str              # task title (required)
due: str | None         # ISO date or datetime
description: str | None # task description (markdown)
tag: str | None         # tag name (comma-separated)
list_name: str | None   # task list name (area of focus)
project: str | None     # project name (added to description)
ref: str | None         # reference URL (added to description)
priority: int | None    # priority (0-9)
```

### `gm_tasks_update`

```
task_id: str            # task ID (required)
title: str | None       # new title
due: str | None         # new due date
description: str | None # replace description entirely
tag: str | None         # replace tags (comma-separated names)
list_name: str | None   # move to list (by name)
project: str | None     # replace project: line in description
ref: str | None         # replace ref: line in description
priority: int | None    # new priority
```

### `gm_tasks_close` / `gm_tasks_reopen` / `gm_tasks_delete`

```
task_id: str            # task ID (required)
```

### `gm_tasks_move`

```
task_id: str            # task ID (required)
after: str | None       # place after this task ID
parent: str | None      # nest under this parent task ID
```

### `gm_tasks_schedule`

```
task_id: str            # task ID (required)
start: str              # ISO 8601 start datetime (required)
duration_minutes: int | None  # override task's estimated duration
timezone: str | None    # e.g. "Europe/Paris" (default: system local)
```

### `gm_events_create`

```
title: str              # event title (required)
start: str              # ISO 8601 start datetime (required)
duration_minutes: int   # duration in minutes (default 30)
description: str | None # event description
timezone: str | None    # e.g. "Europe/Paris" (default: system local)
```

### `gm_events_update`

```
event_id: str           # event ID (required)
title: str | None       # new title
start: str | None       # new start datetime
duration_minutes: int | None  # new duration in minutes
description: str | None # new description
series_mode: str | None # "single", "future", or "all" (recurring events)
```

### `gm_events_delete`

```
event_id: str           # event ID (required)
series_mode: str | None # "single", "future", or "all" (recurring events)
```

### `gm_events_rsvp`

```
event_id: str           # event ID (required)
action: str             # "accept", "decline", or "tentative" (required)
comment: str | None     # optional comment to organiser
notify: bool = True     # notify the organiser
series_mode: str | None # "single", "future", or "all" (recurring events)
```

### `gm_tags_create`

```
name: str               # tag name (required)
color: str | None       # hex colour (e.g. "#ff0000")
```

### `gm_tags_update`

```
tag_id: str             # tag ID (required)
name: str | None        # new name
color: str | None       # new hex colour
```

### `gm_tags_delete`

```
tag_id: str             # tag ID (required)
```

### `gm_lists_create`

```
name: str               # list name (required)
color: str | None       # hex colour (e.g. "#38c2c7")
```

### `gm_lists_update`

```
list_id: str            # list ID (required)
name: str | None        # new name
color: str | None       # new hex colour
```

### `gm_lists_delete`

```
list_id: str            # list ID (required)
```

## Error Handling

All tools return JSON. On error, the response includes:

```json
{"error": "message", "suggestion": "optional hint"}
```

Errors are also logged to stderr.

## Architecture

Handler + wrapper pattern:
- **Handlers** (`handle_gm_*`) — testable functions that receive a `MorgenClient` and return JSON strings. All business logic lives here.
- **Wrappers** (`@mcp.tool()`) — thin MCP transport adapters that create the client singleton and delegate to handlers.
- **Resources** (`@mcp.resource()`) — static data endpoints reusing the same handlers.

Concise field projections (`_EVENT_CONCISE_FIELDS`, `_TASK_CONCISE_FIELDS`) strip description bodies and internal fields from list responses, keeping context usage low.

Unscheduled task capping (default 20) prevents context overflow. A `meta.unscheduled_truncated` flag signals when tasks were capped.

## Troubleshooting

### Proxy errors / SSL failures

Claude Code's sandbox injects SOCKS proxy env vars that break `httpx`. The MCP server strips these automatically at startup (`ALL_PROXY`, `FTP_PROXY`, `GRPC_PROXY`, etc.).

### Server fails to start

Use the full absolute path to `gm-mcp` in Claude Desktop config:

```bash
which gm-mcp
# e.g. /Users/you/.local/bin/gm-mcp
```
