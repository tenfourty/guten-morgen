# MCP Server for guten-morgen

**Date:** 2026-03-11
**Status:** Design (reviewed, CLI parity pass)
**Author:** gm-dev agent

## Context

guten-morgen (`gm`) is a CLI wrapping the Morgen API for calendar and task management. It's optimised for LLM consumption (structured JSON, concise output modes). Currently, AI agents interact with gm exclusively through shell commands (`Bash` tool).

Adding an MCP (Model Context Protocol) server would let AI agents call gm capabilities directly as typed tools — no shell parsing, no stdout scraping, structured JSON in and out. The kbx project already ships an MCP server (`kb/mcp_server.py`) and provides a working reference for architecture, packaging, and configuration.

## Goals

1. **Full CLI parity** — every `gm` CLI capability reachable via MCP (interface may differ)
2. Reuse the existing `MorgenClient` and enrichment pipeline — no duplication
3. Keep the MCP server as an optional dependency (`gm[mcp]`)
4. Follow the kbx pattern: testable handler functions + thin FastMCP wrappers
5. **Context-safe by default** — all list tools use concise output and bounded limits to prevent context window blowout

## Non-Goals

- Replacing the CLI (MCP and CLI coexist; CLI remains the primary interface)
- Exposing every CLI option verbatim (MCP tools are opinionated — concise defaults, sensible limits)
- Adding async support (Morgen API client is sync httpx; FastMCP handles the async bridge)

---

## Tool Selection

### What agents actually do with gm

From observing CoS, brief-deck, and ad-hoc agent usage, the most frequent operations are:

| Operation | Frequency | CLI equivalent |
|-----------|-----------|----------------|
| List today's events + tasks | Very high | `gm today --json` |
| Next upcoming event(s) | Very high | `gm next --json` |
| List/filter tasks | Very high | `gm tasks list --json` |
| Get a single task | High | `gm tasks get ID --json` |
| Create a task | High | `gm tasks create --title ... --due ...` |
| Close a task | High | `gm tasks close ID` |
| Update a task | Medium | `gm tasks update ID --title ...` |
| Find available slots | Medium | `gm availability --date ...` |
| List events in range | Medium | `gm events list --start ... --end ...` |
| Schedule a task (time-block) | Medium | `gm tasks schedule ID --start ...` |
| RSVP to event | Low-Medium | `gm events rsvp ID --action accept` |
| Create an event | Low | `gm events create --title ... --start ...` |
| List task lists | Low (setup) | `gm lists list --json` |
| List tags | Low (setup) | `gm tags list --json` |

### Proposed MCP tools (29 tools)

Grouped by domain. All tools return JSON. **All list tools use concise output by default** — trimmed field sets, no raw description bodies, bounded limits.

#### Calendar / scheduling tools

1. **`gm_today`** — Combined events + tasks for today (the daily snapshot)
   - Params: `group: str | None = None`, `events_only: bool = False`, `tasks_only: bool = False`, `max_unscheduled: int = 20`
   - Returns: `{events, scheduled_tasks, overdue_tasks, unscheduled_tasks, meta: {unscheduled_truncated: bool, unscheduled_total: int}}`
   - Events use concise field set: `id, title, start, duration, my_status, participants_display, location_display`
   - Tasks use concise field set: `id, title, progress, due, source, tag_names, list_name, project`
   - `unscheduled_tasks` is capped at `max_unscheduled` (default 20). When truncated, `meta.unscheduled_truncated = true` and `meta.unscheduled_total` gives the real count. Agents can call `gm_tasks_list` for the full list.
   - This is the single highest-value tool — used at the start of every agent session

2. **`gm_next`** — Next upcoming events (lightweight alternative to `gm_today`)
   - Params: `count: int = 3`, `hours: int = 24`
   - Returns: list of concise events (same trimmed field set as `gm_today`)
   - Cheaper than `gm_today` — fewer API calls, ideal for "what's my next meeting?"

3. **`gm_this_week`** — Combined events + tasks for the current week (Mon–Sun)
   - Params: `group: str | None = None`, `events_only: bool = False`, `tasks_only: bool = False`, `max_unscheduled: int = 20`
   - Returns: same shape as `gm_today` — `{events, scheduled_tasks, overdue_tasks, unscheduled_tasks, meta}`
   - Same concise field sets and unscheduled cap as `gm_today`
   - Used for weekly planning sessions

4. **`gm_this_month`** — Combined events + tasks for the current month
   - Params: `group: str | None = None`, `events_only: bool = False`, `tasks_only: bool = False`, `max_unscheduled: int = 20`
   - Returns: same shape as `gm_today` — `{events, scheduled_tasks, overdue_tasks, unscheduled_tasks, meta}`
   - Same concise field sets and unscheduled cap as `gm_today`
   - Used for monthly planning and review

5. **`gm_events_list`** — List events in a date range
   - Params: `start: str`, `end: str`, `group: str | None = None`
   - Returns: concise enriched event list: `id, title, start, duration, my_status, participants_display, location_display`
   - No raw description bodies

6. **`gm_events_create`** — Create a calendar event
   - Params: `title: str`, `start: str`, `duration_minutes: int`, `description: str | None = None`, `meet: bool = False`, `privacy: str | None = None`
   - Returns: `{status: "ok", event_id: str, title: str}`

7. **`gm_events_update`** — Update an existing calendar event
   - Params: `event_id: str`, `title: str | None = None`, `start: str | None = None`, `duration_minutes: int | None = None`, `description: str | None = None`, `privacy: str | None = None`, `series: str | None = None`
   - `series`: for recurring events — `"single"` (this occurrence), `"future"` (this and future), `"all"` (entire series). Defaults to `None` (non-recurring).
   - Returns: `{status: "ok", event_id: str, title: str}`

8. **`gm_events_delete`** — Delete a calendar event
   - Params: `event_id: str`, `series: str | None = None`
   - `series`: same as `gm_events_update` — `"single"`, `"future"`, or `"all"` for recurring events
   - Returns: `{status: "ok", event_id: str}`

9. **`gm_events_rsvp`** — RSVP to a calendar event
   - Params: `event_id: str`, `action: str` (accept/decline/tentative), `comment: str | None = None`
   - Returns: `{status: "ok", event_id: str, action: str}`

10. **`gm_availability`** — Find available time slots on a date
    - Params: `date: str`, `min_duration_minutes: int = 30`, `start_hour: str | None = None`, `end_hour: str | None = None`, `group: str | None = None`
    - Returns: list of `{start, end, duration_minutes}`

#### Task tools

11. **`gm_tasks_list`** — List tasks with filtering
    - Params: `status: str = "open"`, `overdue: bool = False`, `source: str | None = None`, `tag: str | None = None`, `list_name: str | None = None`, `project: str | None = None`, `limit: int = 25`
    - Returns: concise enriched task list: `id, title, progress, due, source, tag_names, list_name, project`
    - No raw description bodies. Limit defaults to 25, max 100.

12. **`gm_tasks_get`** — Get a single task by ID
    - Params: `task_id: str`
    - Returns: full enriched task dict (including description — this is the detail view)

13. **`gm_tasks_create`** — Create a task
    - Params: `title: str`, `due: str | None = None`, `priority: int | None = None`, `description: str | None = None`, `duration_minutes: int | None = None`, `tag: str | None = None`, `list_name: str | None = None`, `project: str | None = None`
    - Returns: `{status: "ok", task_id: str, title: str}`

14. **`gm_tasks_update`** — Update a task
    - Params: `task_id: str`, `title: str | None = None`, `due: str | None = None`, `priority: int | None = None`, `description: str | None = None`, `duration_minutes: int | None = None`, `tag: str | None = None`, `list_name: str | None = None`, `project: str | None = None`
    - Returns: `{status: "ok", task_id: str, title: str}`

15. **`gm_tasks_close`** — Mark a task as completed
    - Params: `task_id: str`
    - Returns: `{status: "ok", task_id: str}`

16. **`gm_tasks_reopen`** — Reopen a completed task
    - Params: `task_id: str`
    - Returns: `{status: "ok", task_id: str}`

17. **`gm_tasks_delete`** — Delete a task
    - Params: `task_id: str`
    - Returns: `{status: "ok", task_id: str}`

18. **`gm_tasks_move`** — Reorder or nest a task
    - Params: `task_id: str`, `after: str | None = None`, `parent: str | None = None`
    - `after`: place after this task ID in the list. `parent`: nest under this task ID.
    - Returns: `{status: "ok", task_id: str}`

19. **`gm_tasks_schedule`** — Schedule a task as a linked calendar time block
    - Params: `task_id: str`, `start: str`, `duration_minutes: int | None = None`
    - Returns: `{status: "ok", event_id: str, title: str}` — the created calendar event's ID and title
    - Note: this creates a calendar event linked back to the task via `morgen.so:metadata.taskId`

#### Tag management tools

20. **`gm_tags`** — List tags (lifecycle status)
    - No params
    - Returns: list of `{id, name, color}`

21. **`gm_tags_create`** — Create a new tag
    - Params: `name: str`, `color: str | None = None`
    - Returns: `{status: "ok", tag_id: str, name: str}`

22. **`gm_tags_update`** — Update a tag
    - Params: `tag_id: str`, `name: str | None = None`, `color: str | None = None`
    - Returns: `{status: "ok", tag_id: str, name: str}`

23. **`gm_tags_delete`** — Delete a tag
    - Params: `tag_id: str`
    - Returns: `{status: "ok", tag_id: str}`

#### List (area of focus) management tools

24. **`gm_lists`** — List task lists (areas of focus)
    - No params
    - Returns: list of `{id, name, color}`

25. **`gm_lists_create`** — Create a task list
    - Params: `name: str`, `color: str | None = None`
    - Returns: `{status: "ok", list_id: str, name: str}`

26. **`gm_lists_update`** — Update a task list
    - Params: `list_id: str`, `name: str | None = None`, `color: str | None = None`
    - Returns: `{status: "ok", list_id: str, name: str}`

27. **`gm_lists_delete`** — Delete a task list
    - Params: `list_id: str`
    - Returns: `{status: "ok", list_id: str}`

#### Account / configuration tools

28. **`gm_accounts`** — List connected calendar accounts
    - No params
    - Returns: list of `{id, name, email, integrationId, integrationGroups}`

29. **`gm_groups`** — List configured calendar groups
    - No params
    - Returns: `{groups: {name: {accounts: [...], calendars: [...]}}, default_group: str | null}`
    - Agents need this to know valid `group` values for `gm_today`, `gm_events_list`, etc.

### What's deliberately excluded

- **Calendar CRUD** (`gm calendars update`) — admin operation, rarely needed by agents
- **Provider listing** (`gm providers`) — setup/diagnostic only

### MCP resources

Resources are injected into context on connection, so only small, stable reference data qualifies. Dynamic data (today's schedule, task lists) stays as tools only.

| URI | Description |
|-----|-------------|
| `gm://lists` | Task lists (areas of focus) — small, stable, useful for routing |
| `gm://tags` | Tags (lifecycle status) — small, stable, useful for task creation |
| `gm://groups` | Calendar groups — small, stable, agents need valid group names |

---

## Context window safety

All MCP tools are designed to be context-safe by default:

| Concern | Mitigation |
|---------|-----------|
| Large unscheduled task lists | `gm_today`, `gm_this_week`, `gm_this_month` all cap at `max_unscheduled=20`, return `truncated` flag |
| Verbose event/task objects | All list tools use concise field sets — no description bodies |
| Unbounded list queries | `gm_tasks_list` defaults to `limit=25`, max 100 |
| Raw HTML in descriptions | Only `gm_tasks_get` returns description (converted to markdown) |
| Resource auto-injection bloat | Only `gm://lists`, `gm://tags`, `gm://groups` as resources (tiny, static) |
| Week/month event volume | Concise field sets keep per-event token cost low even over longer ranges |

### Concise field sets

**Events (concise):** `id, title, start, duration, my_status, participants_display, location_display`
- Dropped: `description, calendarId, accountId, participants (raw), locations (raw), showAs, showWithoutTime, privacy, freeBusyStatus, timeZone, morgen_metadata, calendar_uid`

**Tasks (concise):** `id, title, progress, due, source, tag_names, list_name, project`
- Dropped: `description, status, priority, createdAt, updatedAt, completedAt, parentId, tags (raw IDs), taskListId, estimatedDuration, integrationId, accountId, labels, links, occurrenceStart, position, earliestStart, descriptionContentType, source_id, source_url, source_status, refs`

**Tasks (full — `gm_tasks_get` only):** All enriched fields including `description` (markdown), `refs`, `source_status`, `source_url`

---

## Error handling

All tools return JSON. On error, the response shape is:

```json
{
  "error": "Human-readable error message",
  "suggestion": "Actionable fix or next step (optional, may be null)"
}
```

Matches kbx's error contract. Errors are also logged to stderr. MCP clients get structured error responses, never raw exceptions.

Examples:
- `{"error": "Task not found: abc123", "suggestion": "Check the task ID with gm_tasks_list"}`
- `{"error": "Authentication failed", "suggestion": "Set MORGEN_API_KEY or check config"}`
- `{"error": "Rate limit exceeded. Retry after 15s", "suggestion": "Wait 15 seconds before retrying"}`

---

## Architecture

### File structure

```
src/guten_morgen/
  mcp_server.py    # NEW — handler functions + FastMCP server
```

Single file, following kbx's pattern exactly. No new modules needed.

### Design pattern: handler + wrapper

```python
# 1. Testable handler — receives client, returns JSON string
def handle_gm_today(client: MorgenClient, config: MorgenConfig, ...) -> str:
    """Combined events + tasks for today. Returns JSON string."""
    ...

# 2. Thin FastMCP wrapper — creates client, calls handler
@mcp.tool()
def gm_today(group: str | None = None, ...) -> str:
    """Today's events and tasks — daily snapshot for agent sessions."""
    client, config = _get_client_and_config()
    return handle_gm_today(client, config, ...)
```

This is the exact pattern kbx uses (`handle_kb_search` → `kb_search`). Benefits:
- Handlers are testable without MCP transport
- Client lifecycle managed in one place
- FastMCP wrappers are trivially thin

### Client lifecycle

```python
_client: MorgenClient | None = None
_morgen_config: MorgenConfig | None = None

def _get_client_and_config() -> tuple[MorgenClient, MorgenConfig]:
    """Lazy singleton — created on first call, reused across tool invocations."""
    global _client, _morgen_config
    if _client is None:
        settings = load_settings()
        cache_store = DiskCache(...)
        _client = MorgenClient(settings, cache=cache_store)
        _morgen_config = load_morgen_config()
    return _client, _morgen_config
```

The MCP server runs as a long-lived process (stdio transport), so we reuse one `MorgenClient` with its built-in cache. This means the httpx client connection pool is shared across tool calls — efficient.

### Reuse of existing internals

The MCP handlers will reuse:
- **`MorgenClient`** — all API calls (events, tasks, calendars, tags, lists)
- **`enrich_events()`** / **`enrich_tasks()`** — add display fields and source metadata
- **`list_enriched_tasks()`** — the convenience wrapper combining `list_all_tasks()` + `enrich_tasks()`
- **`resolve_filter()`** — calendar group resolution
- **`load_morgen_config()`** / **`load_settings()`** — config and auth
- **`html_to_markdown()`** / **`markdown_to_html()`** — description format conversion

No new business logic needed. The handlers orchestrate existing functions and serialise to JSON.

### Concise projection helpers

New shared functions for projecting concise field sets from enriched dicts:

```python
_EVENT_CONCISE_FIELDS = {"id", "title", "start", "duration", "my_status", "participants_display", "location_display"}
_TASK_CONCISE_FIELDS = {"id", "title", "progress", "due", "source", "tag_names", "list_name", "project"}

def _concise_event(event: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in event.items() if k in _EVENT_CONCISE_FIELDS}

def _concise_task(task: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in task.items() if k in _TASK_CONCISE_FIELDS}
```

### Tag/list name resolution

The CLI resolves tag names → IDs and list names → IDs in the Click commands. The MCP handlers need the same logic. Rather than duplicating, extract the resolution helpers:

```python
def _resolve_tag_id(client: MorgenClient, name: str) -> str | None:
    """Find tag ID by name (case-insensitive)."""
    for tag in client.list_tags():
        if tag.name.lower() == name.lower():
            return tag.id
    return None

def _resolve_list_id(client: MorgenClient, name: str) -> str | None:
    """Find task list ID by name (case-insensitive)."""
    for tl in client.list_task_lists():
        if tl.name.lower() == name.lower():
            return tl.id
    return None
```

These currently live inline in `cli.py`. As part of MCP work, extract them to `output.py` or a new `resolve.py` so both CLI and MCP can use them. Small, targeted refactor.

### Calendar/account auto-discovery

For event creation and task scheduling, the CLI auto-discovers the calendar ID and account ID from config. The MCP server needs the same logic. The existing `_resolve_task_calendar()` pattern in cli.py does this — extract it for shared use.

### Availability calculation

The CLI computes availability by scanning events and finding gaps. This logic lives in the `availability` Click command. Extract the core calculation into a function that takes events + time bounds and returns slots.

---

## Tricky parts

### 1. Authentication

The MCP server inherits gm's existing auth chain:
- `$MORGEN_API_KEY` env var → config TOML `api_key`
- Bearer token auto-detected from Morgen desktop app (higher rate limit)

No changes needed. The MCP process inherits the environment of its launcher (Claude Code, Claude Desktop). The existing `load_settings()` handles everything.

**Risk:** Claude Desktop launches with minimal PATH/env. Document that `MORGEN_API_KEY` must be set in the MCP config's `env` block if not using a config file discoverable from the server's CWD.

### 2. Caching

The `MorgenClient` has a built-in TTL cache (`DiskCache`). In CLI mode, the cache directory is `~/.cache/guten-morgen/`. In MCP mode, the same cache should be used.

**Consideration:** The CLI creates `DiskCache` in the Click context. The MCP server needs to create it independently. Extract cache creation to a shared helper.

**Cache warm-up:** The first `gm_today` call in a session hits multiple endpoints (accounts, calendars, events, tasks, tags, lists). Subsequent calls benefit from cache. No special warm-up needed — the cache fills naturally.

### 3. Proxy stripping (mandatory)

The MCP entry point **must** strip SOCKS proxy env vars that Claude Code's sandbox injects. Without this, httpx fails to connect to the Morgen API. kbx does the same in its CLI startup.

```python
def main() -> None:
    """Run the MCP server on stdio transport."""
    # Strip proxy env vars injected by Claude Code sandbox
    for var in ("ALL_PROXY", "all_proxy", "FTP_PROXY", "ftp_proxy",
                "GRPC_PROXY", "grpc_proxy", "RSYNC_PROXY"):
        os.environ.pop(var, None)
    mcp.run(transport="stdio")
```

### 4. Sync vs async

FastMCP handles async/sync bridging. The `MorgenClient` uses sync httpx. FastMCP's `@mcp.tool()` decorator works with sync functions (it runs them in a thread pool). No changes needed.

If we ever want async performance (parallel event + task fetches), we'd need an async httpx client. That's a larger refactor and not needed now.

### 5. The combined view (today / this-week / this-month)

`gm today`, `gm this-week`, and `gm this-month` share the same orchestration pattern:
- Fetch events for a date range (with group filtering, frame exclusion, declined filtering)
- Fetch all tasks (with enrichment)
- Categorise tasks into: scheduled (due in range), overdue, unscheduled
- Cap unscheduled tasks and track truncation
- Project concise field sets

This logic is currently in the Click commands. Extract into a shared `_handle_combined_view(client, config, start, end, ...)` function that all three MCP tools call with different date ranges. This is the biggest single extraction — probably 80-100 lines of pure logic, but it's shared across three tools.

### 6. Rate limiting

Morgen API has rate limits (100 pts/15 min with API key, 500 pts/15 min with bearer). The `MorgenClient` already handles 429 responses with retry + backoff. No additional handling needed in MCP layer.

---

## Installation and configuration

### Optional dependency

```toml
# pyproject.toml
[project.optional-dependencies]
mcp = ["mcp>=1.2"]
```

Install: `pip install "guten-morgen[mcp]"` or `uv tool install "guten-morgen[mcp]"`

### CLI entry point

```python
# cli.py — new command
@cli.command()
def mcp() -> None:
    """Start MCP server on stdio transport."""
    from guten_morgen.mcp_server import main as mcp_main
    mcp_main()
```

Lazy import so `mcp` dependency only needed when the command is invoked.

### Console script (optional)

```toml
[project.scripts]
gm = "guten_morgen.cli:cli"
gm-mcp = "guten_morgen.mcp_server:main"   # direct entry point
```

Having both `gm mcp` (subcommand) and `gm-mcp` (direct) gives flexibility for MCP client config.

### Claude Code configuration

`.claude/settings.local.json`:
```json
{
  "mcpServers": {
    "gm": {
      "command": "gm",
      "args": ["mcp"],
      "type": "stdio"
    }
  }
}
```

### Claude Desktop configuration

```json
{
  "mcpServers": {
    "gm": {
      "command": "/Users/YOU/.local/bin/gm",
      "args": ["mcp"],
      "env": {
        "MORGEN_API_KEY": "your-key-here"
      }
    }
  }
}
```

Full path required (Claude Desktop's minimal PATH). API key in `env` block if no config file at known path.

---

## Implementation approach

### Phase 1: Scaffolding + read-only tools (MVP)

1. Extract shared helpers from `cli.py` (tag/list resolution, calendar discovery, availability calc, today/week/month orchestration)
2. Create `mcp_server.py` with:
   - Concise projection helpers (`_concise_event`, `_concise_task`)
   - Proxy stripping in entry point
   - Client lifecycle singleton
3. Read-only tools:
   - `gm_today`, `gm_next`, `gm_this_week`, `gm_this_month`
   - `gm_events_list`, `gm_availability`
   - `gm_tasks_list`, `gm_tasks_get`
   - `gm_lists`, `gm_tags`
   - `gm_accounts`, `gm_groups`
4. Add `mcp` optional dependency + CLI command + console script
5. Write tests for handler functions (using mock client)
6. Add documentation (`docs/mcp.md`)

### Phase 2: Event + task mutations

7. Event mutation tools:
   - `gm_events_create`, `gm_events_update`, `gm_events_delete`, `gm_events_rsvp`
8. Task mutation tools:
   - `gm_tasks_create`, `gm_tasks_update`, `gm_tasks_close`, `gm_tasks_reopen`
   - `gm_tasks_delete`, `gm_tasks_move`, `gm_tasks_schedule`
9. Tests for all mutation handlers

### Phase 3: Tag/list CRUD + resources

10. Tag CRUD: `gm_tags_create`, `gm_tags_update`, `gm_tags_delete`
11. List CRUD: `gm_lists_create`, `gm_lists_update`, `gm_lists_delete`
12. MCP resources: `gm://lists`, `gm://tags`, `gm://groups`
13. Tests for CRUD handlers + resources

---

## Testing strategy

Follow kbx's approach:
- **Handler tests** — test `handle_gm_*` functions directly with mock `MorgenClient`
- **No transport tests** — don't test FastMCP wiring (that's FastMCP's job)
- **Reuse existing test fixtures** — the test suite already has extensive mock responses

Example:
```python
def test_handle_gm_today(mock_client, mock_config):
    result = json.loads(handle_gm_today(mock_client, mock_config))
    assert "events" in result
    assert "overdue_tasks" in result
    assert "meta" in result

def test_gm_today_truncates_unscheduled(mock_client, mock_config):
    # Mock 30 unscheduled tasks
    result = json.loads(handle_gm_today(mock_client, mock_config, max_unscheduled=5))
    assert len(result["unscheduled_tasks"]) == 5
    assert result["meta"]["unscheduled_truncated"] is True
    assert result["meta"]["unscheduled_total"] == 30

def test_concise_event_projection():
    full = {"id": "1", "title": "Meeting", "start": "...", "description": "long text..."}
    concise = _concise_event(full)
    assert "description" not in concise
    assert "title" in concise

def test_error_shape():
    result = json.loads(handle_gm_tasks_get(mock_client, mock_config, task_id="nonexistent"))
    assert "error" in result
    assert "suggestion" in result or result.get("suggestion") is None
```

---

## Estimated scope

| Component | Lines (approx) | Effort |
|-----------|----------------|--------|
| Helper extraction from cli.py | ~100 | Small refactor |
| Concise projection + truncation | ~40 | Small |
| `mcp_server.py` — Phase 1 (read-only, 12 tools) | ~350 | Medium |
| `mcp_server.py` — Phase 2 (mutations, 11 tools) | ~250 | Medium |
| `mcp_server.py` — Phase 3 (CRUD + resources, 6 tools + 3 resources) | ~120 | Small |
| Tests (all phases) | ~500 | Medium |
| Documentation | ~150 | Small |
| pyproject.toml + CLI command | ~15 | Trivial |

Total: ~1500-1600 lines of new/moved code across all phases. 29 tools + 3 resources.
