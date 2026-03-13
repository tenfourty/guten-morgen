# guten-morgen CLI

Calendar and task management CLI wrapping the Morgen API. All commands emit structured JSON.

## Agent Startup

Run these on first use in a session to orient:

```bash
gm --help                                              # full command reference (the LLM API contract)
gm accounts --json                                    # connected accounts (Google, Outlook, etc.)
gm groups --json                                      # configured calendar groups
gm today --json --response-format concise             # today's calendar + tasks
gm tasks list --status open --json --response-format concise  # all open tasks
gm tags list --json                                   # available tags (Right-Now, Active, etc.)
gm lists list --json --response-format concise        # task lists (Inbox, Run - Work, etc.)
```

## Setup

```bash
uv sync --all-extras && uv run pre-commit install   # first time
cp config.toml.example guten-morgen.toml               # then add api_key (or run gm init)
uv run pytest -x -q --cov && uv run mypy src/       # verify
uv run gm --help                                     # CLI self-documentation
uv tool install --editable .                         # optional: global `gm` command
```

Pre-commit hooks enforce everything (ggshield, ruff, mypy, bandit, pytest+cov). Trust the hooks.

Also install pre-push hooks for portable lint checks:
```bash
uv run pre-commit install --hook-type pre-push
```

## Local CI

```bash
make ci          # full CI mirror (lint → typecheck → security → test)
make lint        # ruff check + format only
make fix         # auto-fix lint issues
make typecheck   # mypy
make security    # bandit
make test        # pytest with coverage
```

`scripts/ci-local.sh --fix` is the standalone equivalent (no Make required).

## TDD Workflow

Every new feature must have:
1. **A happy-path integration test** — exercises `MorgenClient` against a respx transport mock that returns realistic API payloads. Tests the full request/response/enrichment pipeline, not just isolated functions.
2. **A happy-path E2E test** — a subprocess smoke test invoking `gm <command> --json` as a real process against a mock server (or with `--no-cache` + recorded fixtures) and asserting on stdout JSON + exit code.

**TDD order is mandatory:**
- Write integration and E2E tests first (red), then implement until they pass (green)
- When fixing a bug: write a test that reproduces the bug first, then fix the code
- Never write implementation code before a failing test exists

**Exceptions (must be explicitly noted in a comment, not silently skipped):**
- Pure infrastructure (retry logic, rate-limit backoff, cache TTL) — unit test only is acceptable
- MCP handler functions — handler unit tests with mock `MorgenClient` are sufficient; do not test FastMCP transport wiring (that's FastMCP's responsibility)
- Auth token discovery (`auth.py`) — unit only; live OAuth flows are not testable in CI

Quick commands:
```bash
uv run pytest tests/test_tasks.py::test_name -x -v   # single test
uv run pytest -x -q --cov                             # full suite
```
Then: `uv run mypy src/` — clean before committing.

## Architecture

`client.py` (Pydantic models) → `cli.py` (model_dump() → dicts) → `output.py` (table/json/csv)

**The boundary rule:** client returns models, cli converts with `model_dump()`, output only sees dicts.

**Task enrichment pipeline** (`output.py`): `enrich_tasks()` adds computed fields to raw task dicts:
- `source`, `source_id`, `source_url`, `source_status` — normalised external task metadata
- `tag_names`, `list_name` — resolved from IDs to human-readable names
- `project` — parsed from first `project: <Name>` line in description (str | None)
- `refs` — merged from Morgen API `source_url` + `ref: <url>` lines in description (list of {source, url})
- Source inference via `_infer_source()` — hostname pattern matching for 10 integrations

**Event enrichment pipeline** (`output.py`): `enrich_events()` adds computed fields to raw event dicts:
- `participants_display`, `location_display` — formatted strings
- `my_status` — account owner's participation status
- `is_frame` — True when `my_status is None AND (no participants OR only accountOwner)`. Used by `exclude_frames` filtering.

**`list_enriched_tasks(client)`** — convenience function combining `list_all_tasks()` + `enrich_tasks()` for Python consumers (e.g. brief-deck). Import from `guten_morgen.output`.

**MCP server** (`mcp_server.py`): 31 tools with `ToolAnnotations` (read-only, mutating, destructive hints). Key patterns:
- Handler functions (testable without MCP transport) + thin MCP wrappers (`# pragma: no cover`)
- `_filter_tasks()` — shared filtering logic used by both `handle_gm_tasks_list` and `handle_gm_tasks_count`
- `_resolve_filters()` — resolves tag/list names to IDs for filtering
- `_project_events()` — applies concise or compact projection to events
- `_compact_event()` / `_compact_task()` — minimal projection: no id, strips nulls; `_compact_task` also removes id and null fields
- `compact` param on all 3 snapshot handlers (`gm_today`, `gm_this_week`, `gm_this_month`)
- `exclude_frames` (default True) on snapshot handlers filters `is_frame` events
- `due_before`/`due_after` — date-based task filtering (exclusive, YYYY-MM-DD)
- `order_by` — sort tasks by `due_date`, `tag_priority`, `list_name`, or `title`
- Multi-day availability via `end_date` param (14-day cap)
- Smart unscheduled sort: priority (lower=higher, nulls last) then due date, with truncation to `max_unscheduled` (default 20)
- Four annotation constants: `_READONLY`, `_MUTATING`, `_MUTATING_IDEMPOTENT`, `_DESTRUCTIVE`

**CLI parity with MCP** (v0.23.2):
- `--compact` on `today`, `this-week`, `this-month` — mirrors MCP `compact` param
- `--query TEXT` on `tasks list` — client-side case-insensitive substring search on title + description
- `--end-date` on `availability` — multi-day mode with 14-day cap (matches MCP `end_date`)
- `events get EVENT_ID` — structured single-event detail with participants list and markdown description
- `_combined_view` now sorts unscheduled tasks (priority+due), truncates to 20, emits `meta.unscheduled_truncated`/`unscheduled_total`, and skips completed tasks

**Error handling** (`errors.py`): `output_error()` is typed `-> NoReturn` — mypy proves callers never fall through after an error exit.

Deep dive: [`docs/models.md`](docs/models.md) | [`docs/testing.md`](docs/testing.md)

## File Map

```
src/guten_morgen/
  cli.py        Click commands — boundary layer (model → dict)
  client.py     MorgenClient — typed API wrapper
  models.py     Pydantic v2 models (MorgenModel base)
  output.py     Render pipeline + task/event enrichment (project, refs, source, is_frame)
  mcp_server.py MCP server — 31 tools with annotations, handler functions + wrappers
  markup.py     HTML↔Markdown conversion for task descriptions
  errors.py     Exception hierarchy → structured JSON on stderr
  config.py     XDG config discovery + API settings
  auth.py       Bearer token auth via Morgen desktop app
  time_utils.py Date range helpers
  cache.py      TTL-based request cache
  groups.py     Calendar group filtering from guten-morgen.toml
  retry.py      Rate-limit retry with dual-mode countdown
  __main__.py   python -m guten_morgen entrypoint
```

## Conventions

- mypy strict, Pydantic v2, Python 3.10+
- Coverage minimum 90% — enforced by pre-commit
- **`gm --help` is the LLM API contract** — any command/option change MUST update `_build_llm_contract()` in `cli.py`. If it's not in `--help`, LLMs can't discover it.

## Gotchas

- **Auth priority** — Bearer token (Morgen desktop app) → API key. Bearer gives 500pts/15min (1pt per list call) vs API key's 100pts/15min (10pt per list). Auto-detected from `~/Library/Application Support/Morgen/config.json`. Override with `$MORGEN_BEARER_TOKEN`. Cache at `~/.cache/guten-morgen/_bearer.json`.
- **Config discovery** — `$GM_CONFIG` → `guten-morgen.toml` (walk up from CWD) → `~/.config/guten-morgen/config.toml`. Run `gm init` for first-time setup.
- **Calendar groups** — configured in `guten-morgen.toml` under `[groups.*]`. Use `--group all` to bypass filtering.
- **`morgen.so:metadata`** — Event model aliases this. Use `model_dump(by_alias=True)` for events
- **Completed tasks** — Morgen API only returns completed tasks when `updatedAfter` is passed. `--status completed` and `--status all` auto-inject `updatedAfter=30d`. Use `--since` for custom ranges. Cache is bypassed for `updatedAfter` queries (different results shape).
- **Description metadata convention** — Task descriptions support `project: <Name>` (links task to a project) and `ref: <url>` (adds cross-references). Parsed at enrichment time by `_extract_project()` and `_extract_refs()`. CLI supports `--project` and `--ref` on `tasks create` and `tasks update`. `tasks list` supports `--project` for filtering. Note: `_extract_project()` uses `splitlines()[0]` after regex match to handle Unicode line separators (U+2028, U+2029) that `[^\r\n]+` misses.
- **MCP integer inputs** — MCP JSON transport may send integers where strings are expected (e.g. `start_hour: 9` instead of `"9"`). `_normalize_hour()` coerces via `str(h)` before parsing. Always zero-pad both hours and minutes.
- **Mutation output** — use `model_dump(exclude_none=True)` to avoid null flood
- **`uv.lock`** — must be generated with `UV_INDEX="" uv lock --refresh` to avoid baking in private registries
- **Do NOT reinstall after commits** — `uv tool install --editable .` is a one-time setup. Editable installs pick up code changes automatically. Never re-run it after commits, version bumps, or releases.
