# Multi-Source Tasks & Scheduling — Design

## Problem

The morgen CLI currently only lists Morgen-native tasks. The AI agent needs to see and manage tasks from all connected sources (Morgen, Linear, Notion) through a single, normalized interface. The agent also needs to time-block tasks into the calendar.

## Decisions

- **Unified by default**: All task commands fan out across all connected sources. `--source NAME` filters to one.
- **CLI normalizes, agent stays dumb**: External task metadata (Linear labels, Notion statuses) mapped into common fields by the output layer. Agent never learns source-specific schemas.
- **`tasks schedule` as primary time-blocking primitive**: Agent thinks in tasks, not events. Auto-derives title/duration from task metadata.
- **Dynamic source discovery in `usage`**: Agent discovers connected sources at runtime (cached for days).
- **`task_calendar` config**: Default calendar for time blocks, set once in `.config.toml`.

## 1. Multi-Source Task Listing

### New flags on `tasks list`

- `--source NAME` — Filter to one source: `morgen`, `linear`, `notion`. Default: all.
- `--group-by-source` — Group output by source instead of flat unified list.

### Fan-out behavior

1. Discover task-capable accounts from `/integrations/accounts/list` (cached 7 days)
2. Fan out `GET /tasks/list?accountId=X` per external source + default (Morgen native)
3. Merge into one list, sorted by due date (nulls last), then priority
4. Normalize via `enrich_tasks()` in output.py

### Normalized fields (enrich_tasks)

Every task gets these synthesized fields regardless of source:

| Field | Source | Example |
|-------|--------|---------|
| `source` | `integrationId` | `"linear"` |
| `source_id` | Extracted from labels or task ID | `"ENG-1740"` |
| `source_url` | `links.original.href` | `"https://linear.app/..."` |
| `source_status` | Mapped from labels via labelDefs | `"In Progress"` |

Label resolution: `/tasks/list?accountId=X` responses include `labelDefs` and `spaces` alongside tasks. These decode opaque label values into human-readable strings.

### Concise fields

`[id, title, source, source_id, progress, due, priority]`

## 2. `tasks schedule` Command

```
morgen tasks schedule <task-id> --start ISO [--duration MINUTES] [--calendar-id ID]
```

### Behavior

1. Fetch task via `GET /tasks?id=<task-id>`
2. Auto-derive:
   - **title**: from task title (prefixed with source_id if external, e.g. "ENG-1740: Budget planning")
   - **duration**: from `estimatedDuration`, or `--duration`, or 30 min default
   - **calendar**: from `task_calendar` in `.config.toml`, or `--calendar-id`, or auto-discover
   - **timezone**: from task `timeZone` or system default
3. Create event via `POST /events/create` with `morgen.so:metadata: { taskId: <task-id> }`
4. Return: `{ "status": "scheduled", "taskId": "...", "eventId": "...", "start": "...", "duration": "PT30M" }`

### Edge cases

- Task already scheduled (`morgen.so:derived.scheduled = true`): warn but allow (multi-session is valid)
- No `estimatedDuration` and no `--duration`: use 30 min default, note in output

## 3. Updated Combined Views

### `today` / `this-week` / `this-month`

- Call new `list_all_tasks()` instead of `list_tasks()` (fans out across all sources)
- Existing categorization (`scheduled_tasks`, `overdue_tasks`, `unscheduled_tasks`) applies to unified set
- All tasks normalized via `enrich_tasks()`
- No new flags — multi-source is the new default

## 4. Updated `usage` Command

### Dynamic source discovery

```
## Connected Task Sources
- morgen (native inbox + 4 lists, 34 tasks)
- linear (user@example.com, 1 task)
- notion (My Projects, 8 tasks)
```

### Updated recommended workflow

```
1. morgen next --json --response-format concise --no-frames  (what's coming?)
2. morgen today --json --response-format concise --no-frames  (full daily overview, all sources)
3. morgen tasks list --status open --overdue --json           (overdue across all sources)
4. morgen tasks create --title "..." --due ... --duration 30  (create with good metadata)
5. morgen tasks schedule <id> --start ISO                     (time-block a task)
6. morgen tasks close <id>                                    (complete a task)
```

### Scenario docs

```
### Morning Triage
morgen today --json --response-format concise --no-frames
# Returns events + all-source tasks categorized as scheduled/overdue/unscheduled

### Schedule a Linear Issue
morgen tasks list --source linear --json --response-format concise
morgen tasks schedule <task-id> --start 2026-02-18T09:00

### End of Day Review
morgen tasks list --status open --overdue --json --response-format concise

### Create Task with AI Planner Metadata
morgen tasks create --title "Review PR" --due 2026-02-18 --duration 45 --priority 2
# estimatedDuration + priority + due = Morgen AI Planner can auto-schedule
```

## 5. Client & Caching

### New MorgenClient methods

- `list_task_accounts()` — Accounts with `integrationGroups` containing `"tasks"`. Cached 7 days.
- `list_all_tasks(source=None, ...)` — Fan out across all task accounts + native. Merge and return.
- `schedule_task(task_id, start, duration, calendar_id, account_id)` — Fetch task, derive metadata, create linked event.

### Cache TTLs

| Data | TTL | Rationale |
|------|-----|-----------|
| Task accounts | 7 days | Integrations almost never change |
| Per-source task lists | TTL_TASKS | Keyed by accountId |
| Label definitions | 1 day | Label schemas rarely change |

### Rate limit impact

Fan-out across 3 sources = 30 pts (3 x 10). With 100 pts / 15 min, agent can do ~3 full fan-outs per window. Caching makes this a non-issue for repeated calls.

## 6. Config Additions

```toml
# .config.toml
task_calendar = "WyI2NzI4ZTlkY..."  # Calendar ID for time-blocked tasks
```

## Files Changed

- `src/morgen/client.py` — `list_task_accounts()`, `list_all_tasks()`, `schedule_task()`
- `src/morgen/output.py` — `enrich_tasks()` normalization function
- `src/morgen/cli.py` — `--source`, `--group-by-source`, `--duration` flags; `tasks schedule` command; updated `usage()` and `_combined_view()`
- `src/morgen/cache.py` — `TTL_TASK_ACCOUNTS` constant
- `src/morgen/groups.py` — `task_calendar` config field
- `tests/` — Tests for all new methods and commands
