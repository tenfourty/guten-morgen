# XDG-Compatible Configuration

## Problem

`_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent` in `config.py` and `groups.py` points into the virtualenv's site-packages for installed users (`uv tool install`). Config and `.env` discovery silently fail. The tool only works because `$MORGEN_API_KEY` is set in the shell and `MorgenConfig` returns no-op defaults.

Additionally, config is split across two files (`.env` for secrets, `.config.toml` for groups) with no standard discovery.

## Design

### Config File Discovery

Search order (first found wins):

| Priority | Path | Use case |
|----------|------|----------|
| 1 | `$GM_CONFIG` env var | Explicit override (CI, testing) |
| 2 | `./config.toml` (CWD) | Dev/project-local |
| 3 | `$XDG_CONFIG_HOME/guten-morgen/config.toml` | Installed users (default `~/.config/guten-morgen/`) |

If none found, return no-op defaults (same as today). API key still required via env var or config.

### Unified Config Format

Single TOML file replaces both `.env` and `.config.toml`:

```toml
# API credentials (or use $MORGEN_API_KEY env var)
api_key = "mrgn_..."

# Calendar filtering
default_group = "work"
active_only = true

# Task defaults
task_calendar = "Tasks"
task_calendar_account = "user@example.com:google"

[groups.work]
accounts = ["user@example.com:google"]
calendars = ["Jeremy Brown", "Holidays in France"]

[groups.personal]
accounts = ["personal@example.com:fastmail"]
calendars = ["Jeremy"]
```

### API Key Resolution

| Priority | Source |
|----------|--------|
| 1 | `$MORGEN_API_KEY` env var (always wins) |
| 2 | `api_key` in resolved config TOML |

### Cache

No change. Stays at `~/.cache/guten-morgen/`. Already XDG-compliant.

### `gm init` Command

Interactive setup for new users:

```
$ gm init
Morgen API key (from https://platform.morgen.so/): mrgn_...
Writing config to ~/.config/guten-morgen/config.toml
Run `gm events today` to verify.
```

Creates the XDG config directory and writes a minimal config file.

## File Changes

| File | Change |
|------|--------|
| `config.py` | Drop `_PROJECT_ROOT`, drop `python-dotenv`. New `find_config()` with 3-step search. `load_settings()` reads API key from env var first, then TOML. |
| `groups.py` | Drop `_PROJECT_ROOT`. `load_morgen_config()` calls shared `find_config()`. |
| `cli.py` | Add `gm init` command. Update `_config_file_path()` to use `find_config()`. Drop `_PROJECT_ROOT` import. |
| `pyproject.toml` | Drop `python-dotenv` dependency. |
| `config.toml.example` | New — replaces `.env.example` + `.config.toml`. |
| `.gitignore` | Add `config.toml`, remove `.env` entries if present. |
| `.env.example`, `.config.toml` | Removed from repo. |

## Backward Compatibility

- `$MORGEN_API_KEY` env var continues to work (highest priority).
- `./config.toml` in CWD means existing `.config.toml` users just rename the file.
- `$MORGEN_CONFIG` env var dropped — use `$GM_CONFIG`.
