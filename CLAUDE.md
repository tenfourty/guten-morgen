# guten-morgen CLI

Calendar and task management CLI wrapping the Morgen API. All commands emit structured JSON.

## Agent Startup

Run these on first use in a session to orient:

```bash
gm usage                                              # full command reference (the LLM API contract)
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
uv run gm usage                                      # CLI self-documentation
uv tool install --editable .                         # optional: global `gm` command
```

Pre-commit hooks enforce everything (ggshield, ruff, mypy, bandit, pytest+cov). Trust the hooks.

## TDD Workflow

1. Write failing test in `tests/`
2. Implement in `src/guten_morgen/`
3. `uv run pytest -x -q` — green, then `uv run mypy src/` — clean

## Architecture

`client.py` (Pydantic models) → `cli.py` (model_dump() → dicts) → `output.py` (table/json/csv)

**The boundary rule:** client returns models, cli converts with `model_dump()`, output only sees dicts.

Deep dive: [`docs/models.md`](docs/models.md) | [`docs/testing.md`](docs/testing.md)

## File Map

```
src/guten_morgen/
  cli.py        Click commands — boundary layer (model → dict)
  client.py     MorgenClient — typed API wrapper
  models.py     Pydantic v2 models (MorgenModel base)
  output.py     Render pipeline (table/json/jsonl/csv + fields + jq)
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
- **`gm usage` is the LLM API contract** — any command/option change MUST update the `usage()` docstring in `cli.py`. If it's not in `usage`, LLMs can't discover it.

## Gotchas

- **Auth priority** — Bearer token (Morgen desktop app) → API key. Bearer gives 500pts/15min (1pt per list call) vs API key's 100pts/15min (10pt per list). Auto-detected from `~/Library/Application Support/Morgen/config.json`. Override with `$MORGEN_BEARER_TOKEN`. Cache at `~/.cache/guten-morgen/_bearer.json`.
- **Config discovery** — `$GM_CONFIG` → `guten-morgen.toml` (walk up from CWD) → `~/.config/guten-morgen/config.toml`. Run `gm init` for first-time setup.
- **Calendar groups** — configured in `guten-morgen.toml` under `[groups.*]`. Use `--group all` to bypass filtering.
- **`morgen.so:metadata`** — Event model aliases this. Use `model_dump(by_alias=True)` for events
- **Mutation output** — use `model_dump(exclude_none=True)` to avoid null flood
- **`uv.lock`** — must be generated with `UV_INDEX="" uv lock --refresh` to avoid baking in private registries
