# guten-morgen

A CLI for [Morgen](https://morgen.so) calendar and task management, designed for both humans and LLM agents.

All commands emit structured JSON, making it easy to pipe into scripts, `jq`, or feed directly to AI coding assistants like Claude Code.

## Features

- **Unified task view** — see tasks from Morgen, Linear, and Notion in one place
- **Calendar groups** — filter events by work/personal/family with a single flag
- **Time-blocking** — schedule tasks as calendar events with `tasks schedule`
- **Tag lifecycle** — model task stages (Active, Waiting-On, Someday) with tags
- **LLM-friendly output** — `--json`, `--response-format concise`, `--jq`, `--fields` for token-efficient responses
- **Smart caching** — TTL-based cache with `cache clear` and `cache stats`

## Installation

Requires Python 3.10+.

```bash
# Run without installing (uv)
uvx guten-morgen --help

# Install globally (uv — recommended)
uv tool install guten-morgen

# Install globally (pipx)
pipx install guten-morgen

# Install into current environment (pip)
pip install guten-morgen

# From source (development)
git clone https://github.com/tenfourty/guten-morgen.git
cd guten-morgen
uv sync --all-extras
uv run pre-commit install
```

All methods expose the `gm` command.

## Setup

1. **Get an API key** from [Morgen Platform](https://platform.morgen.so/) (Settings > API Keys)

2. **Create your `.env` file:**
   ```bash
   cp .env.example .env
   # Edit .env and add your MORGEN_API_KEY
   ```

3. **Configure calendar groups** (optional):
   ```bash
   cp .config.toml.example .config.toml
   # Edit .config.toml with your account details
   ```

4. **Verify it works:**
   ```bash
   gm accounts
   gm today --json
   ```

## Quick Start

```bash
# What's coming up?
gm next --json --response-format concise

# Full daily overview
gm today --json

# List overdue tasks across all sources
gm tasks list --status open --overdue --json --group-by-source

# Create and time-block a task
gm tasks create --title "Write design doc" --due 2026-02-20 --duration 90
gm tasks schedule <task-id> --start 2026-02-20T10:00:00

# Filter by tag
gm tasks list --tag "Active" --status open --json
```

Run `gm usage` for the full command reference.

## Calendar Groups

Groups let you filter events by context. Configure in `.config.toml`:

```toml
default_group = "work"
active_only = true

[groups.work]
accounts = ["you@company.com:google"]
calendars = ["Work Calendar"]

[groups.personal]
accounts = ["you@personal.com:fastmail"]
calendars = ["Personal"]
```

Use `--group personal` to switch context, or `--group all` to see everything.

## Global Options

| Option | Description |
|--------|-------------|
| `--format table\|json\|jsonl\|csv` | Output format (default: table) |
| `--json` | Shortcut for `--format json` |
| `--fields <list>` | Select specific fields |
| `--jq <expr>` | jq filtering on output |
| `--response-format concise` | ~1/3 the tokens (great for LLMs) |
| `--short-ids` | Truncate IDs to 12 chars |
| `--group NAME` | Filter by calendar group |
| `--no-cache` | Bypass cache |

## Development

```bash
# Install dev dependencies
uv sync --all-extras
uv run pre-commit install

# Run tests
uv run pytest -x -q --cov

# Type checking
uv run mypy src/

# Lint
uv run ruff check .
```

Pre-commit hooks enforce ruff, mypy, bandit, pytest (90% coverage minimum), and [ggshield](https://github.com/GitGuardian/ggshield) secret scanning. To use ggshield, [create a free account](https://dashboard.gitguardian.com/signup) and set `GITGUARDIAN_API_KEY`.

### Architecture

```
src/guten_morgen/
  cli.py        Click commands — boundary layer (model -> dict)
  client.py     MorgenClient — typed API wrapper (Pydantic models)
  models.py     Pydantic v2 models
  output.py     Render pipeline (table/json/jsonl/csv + fields + jq)
  errors.py     Exception hierarchy -> structured JSON on stderr
  config.py     Settings from .env
  time_utils.py Date range helpers
  cache.py      TTL-based request cache
  groups.py     Calendar group filtering from .config.toml
```

**The boundary rule:** `client.py` returns Pydantic models, `cli.py` converts with `model_dump()`, `output.py` only sees dicts.

## Claude Code Integration

This project includes a `CLAUDE.md` with conventions and a `.claude/` directory with hooks and skills for use with [Claude Code](https://docs.anthropic.com/en/docs/claude-code). These are optional — the CLI works without them.

## License

[MIT](LICENSE)
