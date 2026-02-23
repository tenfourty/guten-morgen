# Task Lists Support

**Date:** 2026-02-24
**Status:** Approved

## Context

Morgen has task lists (Inbox, Run - Work, Routines, etc.) visible in the UI but not exposed in `gm`. The API supports full CRUD on task lists via **v2** endpoints (`https://api.morgen.so/v2/taskLists/*`), while all other `gm` API calls use v3.

Tasks already carry a `taskListId` field in the model but there's no CLI support for reading or setting it.

## API Discovery

| Endpoint | Method | Required fields | Notes |
|---|---|---|---|
| `/v2/taskLists/list` | GET | `limit` param (default is low, use 100) | Returns array of TaskList objects |
| `/v2/taskLists/create` | POST | `name` (string, min length 1) | Also accepts `color` |
| `/v2/taskLists/update` | POST | `id` (string) | Accepts `name`, `color` |
| `/v2/taskLists/delete` | POST | `id` (string) | |

TaskList object schema (from API responses):
```json
{
  "@type": "TaskList",
  "serviceName": "morgen",
  "id": "07134c5c-1183-4f8c-9716-4c58257694c8@morgen.so",
  "name": "Run - Work",
  "color": "#38c2c7",
  "role": null,
  "position": 1761671965352,
  "created": "2025-10-28T17:19:25Z",
  "updated": "2025-10-28T17:19:32.616Z",
  "myRights": { "mayAdmin": true, "mayDelete": true, ... },
  "accountId": null
}
```

Special cases:
- Inbox has `id: "inbox"`, `role: "inbox"`, `mayAdmin: false`, `mayDelete: false`
- All custom lists have full permissions and `@morgen.so` ID suffix

## Design

### 1. Model: `TaskList`

New Pydantic model in `models.py`:

```python
class TaskList(MorgenModel):
    """Task list (project/folder for tasks)."""
    id: str
    name: str
    color: str | None = None
    role: str | None = None
    serviceName: str | None = None
    position: int | None = None
    created: str | None = None
    updated: str | None = None
```

`myRights` and `accountId` are dropped (handled by `extra="ignore"`). The API enforces permissions server-side.

### 2. Client: v2 API methods

Add `V2_BASE_URL = "https://api.morgen.so/v2"` constant in `client.py` (alongside existing `SYNC_BASE_URL`).

New methods on `MorgenClient`:

- `list_task_lists() -> list[TaskList]` — GET `V2_BASE_URL/taskLists/list?limit=100`, cached with `TTL_TAGS` (24h)
- `create_task_list(data) -> TaskList | None` — POST `V2_BASE_URL/taskLists/create`
- `update_task_list(data) -> TaskList | None` — POST `V2_BASE_URL/taskLists/update`
- `delete_task_list(list_id) -> None` — POST `V2_BASE_URL/taskLists/delete`

These pass full absolute URLs to `_request()`, same pattern as RSVP uses `SYNC_BASE_URL`.

Cache invalidation on mutations: invalidate `"taskLists"` prefix.

### 3. CLI: `gm lists` group

New top-level command group mirroring `gm tags`:

```
gm lists list [--json]
gm lists create --name "Project: X" [--color "#hex"]
gm lists update ID [--name TEXT] [--color HEX]
gm lists delete ID
```

Table columns: `id`, `name`, `color`, `role`.
Concise fields: `id`, `name`, `color`.

### 4. CLI: `--list` on task commands

Add `--list` option to:
- `gm tasks create` — sets `taskListId` on the new task
- `gm tasks update` — moves task to a different list
- `gm tasks list` — client-side filter on `taskListId`

Name resolution: `_resolve_list_name(client, name) -> str`
- Case-insensitive match against `list_task_lists()`
- Error if no match found
- Same pattern as `_resolve_tag_names()`

### 5. Task output enrichment

When listing tasks, enrich each task dict with `list_name` by looking up `taskListId` against the task lists cache. This parallels how tasks already get `tag_names`.

### 6. `usage()` docstring

Add `gm lists` commands and `--list` option to the usage docstring in `cli.py`.

## Decisions

- **v2 handling:** Full URL pattern (like RSVP's SYNC_BASE_URL), not a separate client class
- **CLI structure:** `gm lists *` top-level group, not nested under `gm tasks`
- **Name resolution:** By name only (case-insensitive), not raw IDs — keeps it ergonomic
- **Skipped fields:** `myRights`, `accountId` — not useful for CLI, API enforces permissions
