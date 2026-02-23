# XDG Config Migration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace `_PROJECT_ROOT`-based config discovery with XDG-compliant `find_config()`, unify `.env` + `.config.toml` into a single `config.toml`, drop `python-dotenv`, and add `gm init`.

**Architecture:** New `find_config()` in `config.py` searches `$GM_CONFIG` → `./config.toml` → `$XDG_CONFIG_HOME/guten-morgen/config.toml`. Both `load_settings()` and `load_morgen_config()` use it. `gm init` writes a minimal config to the XDG location.

**Tech Stack:** Python 3.10+, tomllib/tomli for reading TOML, Click for CLI, pytest for testing.

**Design doc:** `docs/plans/2026-02-23-xdg-config-design.md`

---

### Task 1: Add `find_config()` to `config.py`

**Files:**
- Modify: `src/guten_morgen/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
from guten_morgen.config import find_config


class TestFindConfig:
    def test_gm_config_env_var(self, tmp_path, monkeypatch):
        cfg = tmp_path / "custom.toml"
        cfg.write_text("api_key = 'test'\n")
        monkeypatch.setenv("GM_CONFIG", str(cfg))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert find_config() == cfg

    def test_gm_config_env_var_missing_file_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GM_CONFIG", str(tmp_path / "nope.toml"))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert find_config() is None

    def test_cwd_config_toml(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.toml"
        cfg.write_text("api_key = 'test'\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert find_config() == cfg

    def test_xdg_config_home(self, tmp_path, monkeypatch):
        xdg = tmp_path / "xdg"
        gm_dir = xdg / "guten-morgen"
        gm_dir.mkdir(parents=True)
        cfg = gm_dir / "config.toml"
        cfg.write_text("api_key = 'test'\n")
        monkeypatch.chdir(tmp_path)  # no config.toml in CWD
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        assert find_config() == cfg

    def test_xdg_default_home(self, tmp_path, monkeypatch):
        home = tmp_path / "fakehome"
        gm_dir = home / ".config" / "guten-morgen"
        gm_dir.mkdir(parents=True)
        cfg = gm_dir / "config.toml"
        cfg.write_text("api_key = 'test'\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", str(home))
        assert find_config() == cfg

    def test_no_config_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "emptyhome"))
        assert find_config() is None

    def test_priority_gm_config_over_cwd(self, tmp_path, monkeypatch):
        env_cfg = tmp_path / "env.toml"
        env_cfg.write_text("api_key = 'from-env'\n")
        cwd_cfg = tmp_path / "config.toml"
        cwd_cfg.write_text("api_key = 'from-cwd'\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GM_CONFIG", str(env_cfg))
        assert find_config() == env_cfg

    def test_priority_cwd_over_xdg(self, tmp_path, monkeypatch):
        cwd_cfg = tmp_path / "config.toml"
        cwd_cfg.write_text("api_key = 'from-cwd'\n")
        xdg = tmp_path / "xdg"
        gm_dir = xdg / "guten-morgen"
        gm_dir.mkdir(parents=True)
        (gm_dir / "config.toml").write_text("api_key = 'from-xdg'\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        assert find_config() == cwd_cfg
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py::TestFindConfig -v`
Expected: FAIL — `find_config` doesn't exist yet

**Step 3: Implement `find_config()`**

Replace the contents of `src/guten_morgen/config.py` with:

```python
"""Configuration: XDG-compliant config discovery and settings."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]

from guten_morgen.errors import ConfigError

_CONFIG_FILENAME = "config.toml"
_APP_DIR = "guten-morgen"


def find_config() -> Path | None:
    """Discover config file using XDG conventions.

    Search order (first existing file wins):
    1. $GM_CONFIG env var
    2. ./config.toml in CWD
    3. $XDG_CONFIG_HOME/guten-morgen/config.toml (default ~/.config/)
    """
    # 1. Explicit env var
    env_path = os.environ.get("GM_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p

    # 2. CWD
    cwd = Path.cwd() / _CONFIG_FILENAME
    if cwd.is_file():
        return cwd

    # 3. XDG
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_home:
        xdg_path = Path(xdg_home) / _APP_DIR / _CONFIG_FILENAME
    else:
        xdg_path = Path.home() / ".config" / _APP_DIR / _CONFIG_FILENAME
    if xdg_path.is_file():
        return xdg_path

    return None


def load_config_toml(path: Path | None = None) -> dict[str, object]:
    """Load and return raw TOML config dict. Empty dict if no file."""
    if path is None:
        path = find_config()
    if path is None or not path.is_file():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


@dataclass
class Settings:
    """Morgen API configuration."""

    api_key: str
    base_url: str = "https://api.morgen.so/v3"
    timeout: float = 30.0


def load_settings() -> Settings:
    """Load settings from env vars and/or config TOML.

    API key priority: $MORGEN_API_KEY env var > api_key in config TOML.
    """
    raw = load_config_toml()

    api_key = os.environ.get("MORGEN_API_KEY") or str(raw.get("api_key", ""))
    if not api_key:
        raise ConfigError(
            "MORGEN_API_KEY is not set",
            suggestions=[
                "Run `gm init` to create a config file",
                "Or set MORGEN_API_KEY in your environment",
            ],
        )

    return Settings(
        api_key=api_key,
        base_url=os.environ.get("MORGEN_BASE_URL", "https://api.morgen.so/v3"),
        timeout=float(os.environ.get("MORGEN_TIMEOUT", "30.0")),
    )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: ALL PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/config.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/guten_morgen/config.py tests/test_config.py
git commit -m "feat: add find_config() with XDG-compliant config discovery"
```

---

### Task 2: Update `load_settings()` tests for TOML-based API key

**Files:**
- Modify: `tests/test_config.py`

**Step 1: Update existing `TestLoadSettings` tests**

The existing tests for `load_settings()` reference `_find_env_file` which no longer exists. Update them:

```python
class TestLoadSettings:
    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("MORGEN_API_KEY", "test-key-123")
        settings = load_settings()
        assert settings.api_key == "test-key-123"

    def test_from_config_toml(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.toml"
        cfg.write_text('api_key = "toml-key-456"\n')
        monkeypatch.setenv("GM_CONFIG", str(cfg))
        monkeypatch.delenv("MORGEN_API_KEY", raising=False)
        settings = load_settings()
        assert settings.api_key == "toml-key-456"

    def test_env_overrides_toml(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.toml"
        cfg.write_text('api_key = "toml-key"\n')
        monkeypatch.setenv("GM_CONFIG", str(cfg))
        monkeypatch.setenv("MORGEN_API_KEY", "env-key")
        settings = load_settings()
        assert settings.api_key == "env-key"

    def test_missing_key_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MORGEN_API_KEY", raising=False)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
        with pytest.raises(ConfigError, match="MORGEN_API_KEY is not set"):
            load_settings()

    def test_missing_key_suggests_gm_init(self, tmp_path, monkeypatch):
        monkeypatch.delenv("MORGEN_API_KEY", raising=False)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
        with pytest.raises(ConfigError) as exc_info:
            load_settings()
        assert "gm init" in exc_info.value.suggestions[0]

    def test_custom_base_url(self, monkeypatch):
        monkeypatch.setenv("MORGEN_API_KEY", "key")
        monkeypatch.setenv("MORGEN_BASE_URL", "https://custom.api.com")
        settings = load_settings()
        assert settings.base_url == "https://custom.api.com"

    def test_custom_timeout(self, monkeypatch):
        monkeypatch.setenv("MORGEN_API_KEY", "key")
        monkeypatch.setenv("MORGEN_TIMEOUT", "60.0")
        settings = load_settings()
        assert settings.timeout == 60.0
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: ALL PASS

**Step 3: Commit**

```bash
git add tests/test_config.py
git commit -m "test: update load_settings tests for TOML-based config"
```

---

### Task 3: Migrate `groups.py` to use `find_config()`

**Files:**
- Modify: `src/guten_morgen/groups.py`
- Modify: `tests/test_groups.py`

**Step 1: Write a failing test for the new discovery**

Add to `tests/test_groups.py`:

```python
class TestLoadMorgenConfigDiscovery:
    """Tests that load_morgen_config uses find_config() when no path given."""

    def test_gm_config_env_var(self, tmp_path, monkeypatch):
        cfg = tmp_path / "custom.toml"
        cfg.write_text("active_only = true\n")
        monkeypatch.setenv("GM_CONFIG", str(cfg))
        config = load_morgen_config()
        assert config.active_only is True

    def test_no_config_returns_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
        config = load_morgen_config()
        assert config.default_group is None
        assert config.groups == {}
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_groups.py::TestLoadMorgenConfigDiscovery -v`
Expected: FAIL — still uses `MORGEN_CONFIG` and `_PROJECT_ROOT`

**Step 3: Update `groups.py`**

Remove `_PROJECT_ROOT`, remove `os` import (if no longer needed), change `load_morgen_config()` to use `find_config()`:

```python
"""Calendar group configuration and filter resolution."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]

from guten_morgen.config import find_config
from guten_morgen.errors import GroupNotFoundError


# ... GroupConfig, MorgenConfig, CalendarFilter unchanged ...


def load_morgen_config(path: Path | None = None) -> MorgenConfig:
    """Load configuration from TOML file.

    Uses find_config() for XDG-compliant discovery when no path given.
    Returns no-op defaults if no config file found.
    """
    if path is None:
        found = find_config()
        if found is None:
            return MorgenConfig()
        path = found

    if not path.exists():
        return MorgenConfig()

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    groups: dict[str, GroupConfig] = {}
    for name, gdata in raw.get("groups", {}).items():
        groups[name] = GroupConfig(
            accounts=gdata.get("accounts", []),
            calendars=gdata.get("calendars") or None,
        )

    return MorgenConfig(
        default_group=raw.get("default_group"),
        active_only=raw.get("active_only", False),
        groups=groups,
        task_calendar=raw.get("task_calendar"),
        task_calendar_account=raw.get("task_calendar_account"),
    )
```

**Step 4: Update old `test_env_var_override` test**

The existing test uses `MORGEN_CONFIG` which is now `GM_CONFIG`. Update in `TestLoadMorgenConfig`:

```python
    def test_env_var_override(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "custom.toml"
        cfg_file.write_text("active_only = true\n")
        monkeypatch.setenv("GM_CONFIG", str(cfg_file))
        config = load_morgen_config()
        assert config.active_only is True
```

**Step 5: Run all tests**

Run: `uv run pytest tests/test_groups.py tests/test_config.py -v`
Expected: ALL PASS

**Step 6: Run mypy**

Run: `uv run mypy src/guten_morgen/groups.py`
Expected: clean

**Step 7: Commit**

```bash
git add src/guten_morgen/groups.py tests/test_groups.py
git commit -m "refactor: migrate groups.py to use find_config() instead of _PROJECT_ROOT"
```

---

### Task 4: Update `cli.py` — drop `_PROJECT_ROOT` import, fix `_config_file_path()`

**Files:**
- Modify: `src/guten_morgen/cli.py`

**Step 1: Update `_config_file_path()`**

Replace lines 393-402 in `cli.py`:

```python
def _config_file_path() -> str:
    """Return the resolved config file path for display."""
    from guten_morgen.config import find_config

    found = find_config()
    if found:
        return str(found)
    return "(not found — run `gm init` to create)"
```

**Step 2: Run existing tests**

Run: `uv run pytest tests/ -v -x`
Expected: ALL PASS (this is a pure internal refactor)

**Step 3: Run mypy**

Run: `uv run mypy src/guten_morgen/cli.py`
Expected: clean

**Step 4: Commit**

```bash
git add src/guten_morgen/cli.py
git commit -m "refactor: drop _PROJECT_ROOT from cli.py, use find_config()"
```

---

### Task 5: Update error messages and suggestions

**Files:**
- Modify: `src/guten_morgen/errors.py`
- Modify: `src/guten_morgen/groups.py` (suggestion text in `resolve_filter`)

**Step 1: Update `errors.py` default suggestions**

In `AuthenticationError`:
```python
    suggestions = [
        "Run `gm init` to create a config file",
        "Or set MORGEN_API_KEY in your environment",
        "Verify the key at https://platform.morgen.so/",
    ]
```

In `ConfigError`:
```python
    suggestions = [
        "Run `gm init` to create a config file",
        "Or set MORGEN_API_KEY in your environment",
    ]
```

**Step 2: Update `resolve_filter` suggestion in `groups.py`**

Change `.config.toml` reference to `config.toml`:
```python
            [f"Available groups: {', '.join(available)}"] if available else ["No groups configured — run `gm init`"]
```

**Step 3: Run full test suite**

Run: `uv run pytest tests/ -v -x`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add src/guten_morgen/errors.py src/guten_morgen/groups.py
git commit -m "fix: update error suggestions to reference gm init instead of .env"
```

---

### Task 6: Add `gm init` command

**Files:**
- Modify: `src/guten_morgen/cli.py`
- Create: `tests/test_cli_init.py`

**Step 1: Write failing tests**

Create `tests/test_cli_init.py`:

```python
"""Tests for gm init command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from guten_morgen.cli import cli


class TestInit:
    def test_creates_xdg_config(self, tmp_path, monkeypatch):
        xdg = tmp_path / "config"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["init"], input="test-api-key-123\n")

        assert result.exit_code == 0
        cfg_path = xdg / "guten-morgen" / "config.toml"
        assert cfg_path.exists()
        content = cfg_path.read_text()
        assert 'api_key = "test-api-key-123"' in content

    def test_refuses_overwrite_without_force(self, tmp_path, monkeypatch):
        xdg = tmp_path / "config"
        gm_dir = xdg / "guten-morgen"
        gm_dir.mkdir(parents=True)
        existing = gm_dir / "config.toml"
        existing.write_text('api_key = "old"\n')
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["init"], input="new-key\n")

        assert result.exit_code == 1
        assert "already exists" in result.output
        assert existing.read_text() == 'api_key = "old"\n'

    def test_force_overwrites(self, tmp_path, monkeypatch):
        xdg = tmp_path / "config"
        gm_dir = xdg / "guten-morgen"
        gm_dir.mkdir(parents=True)
        existing = gm_dir / "config.toml"
        existing.write_text('api_key = "old"\n')
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["init", "--force"], input="new-key\n")

        assert result.exit_code == 0
        content = existing.read_text()
        assert 'api_key = "new-key"' in content

    def test_output_path_shown(self, tmp_path, monkeypatch):
        xdg = tmp_path / "config"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["init"], input="key\n")

        assert result.exit_code == 0
        assert "guten-morgen/config.toml" in result.output

    def test_written_config_is_valid_toml(self, tmp_path, monkeypatch):
        """Config written by init can be loaded by load_morgen_config."""
        import sys
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib

        xdg = tmp_path / "config"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["init"], input="my-key\n")
        assert result.exit_code == 0

        cfg_path = xdg / "guten-morgen" / "config.toml"
        with open(cfg_path, "rb") as f:
            data = tomllib.load(f)
        assert data["api_key"] == "my-key"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_init.py -v`
Expected: FAIL — `init` command doesn't exist

**Step 3: Implement `gm init`**

Add to `src/guten_morgen/cli.py`, after the `usage` command (around line 391):

```python
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
    """Return the XDG config directory for guten-morgen."""
    from pathlib import Path

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
    import os

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
    click.echo('Run `gm events today` to verify.')
```

Note: `import os` is already at the top of `cli.py` — the one inside the function is just for the `_xdg_config_path` helper. Actually, move the `os` import to module level and put the helper before the command.

**Step 4: Run tests**

Run: `uv run pytest tests/test_cli_init.py -v`
Expected: ALL PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/cli.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/guten_morgen/cli.py tests/test_cli_init.py
git commit -m "feat: add gm init command for interactive config setup"
```

---

### Task 7: Update `usage()` docstring with `init` command

**Files:**
- Modify: `src/guten_morgen/cli.py` (usage docstring)
- Test: `tests/test_cli_usage.py` (if it checks command list)

**Step 1: Add `init` to usage text**

In the `usage()` docstring in `cli.py`, add after the `## Commands` header (before `### Accounts`):

```
### Setup
- `gm init [--force]`
  Create config at ~/.config/guten-morgen/config.toml. Prompts for API key.
  --force overwrites an existing file.
```

**Step 2: Run usage tests**

Run: `uv run pytest tests/test_cli_usage.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add src/guten_morgen/cli.py
git commit -m "docs: add gm init to usage docstring"
```

---

### Task 8: Drop `python-dotenv`, clean up repo files

**Files:**
- Modify: `pyproject.toml` — remove `python-dotenv>=1.0` from dependencies
- Delete: `.env.example`
- Delete: `.config.toml` (the example one in repo — **NOT** a user's real config)
- Create: `config.toml.example`
- Modify: `.gitignore`

**Step 1: Update `pyproject.toml`**

Remove `"python-dotenv>=1.0",` from the `dependencies` list.

**Step 2: Create `config.toml.example`**

```toml
# guten-morgen configuration
# Copy to config.toml (in this directory) or ~/.config/guten-morgen/config.toml
# Or run: gm init

# API key from https://platform.morgen.so/
# (or set MORGEN_API_KEY environment variable)
api_key = "your_api_key_here"

# Calendar group filtering
# default_group = "work"
# active_only = true

# [groups.work]
# accounts = ["you@example.com:google"]
# calendars = ["My Calendar"]
```

**Step 3: Update `.gitignore`**

Replace `.env` and `.config.toml` lines with `config.toml`:

```
config.toml
__pycache__/
...
```

**Step 4: Delete old files**

```bash
git rm .env.example .config.toml
```

**Step 5: Sync lock file**

```bash
UV_INDEX="" uv lock --refresh
```

**Step 6: Run full test suite**

Run: `uv run pytest tests/ -v -x --cov`
Expected: ALL PASS, coverage >= 90%

**Step 7: Run mypy**

Run: `uv run mypy src/`
Expected: clean

**Step 8: Commit**

```bash
git add pyproject.toml uv.lock config.toml.example .gitignore
git commit -m "chore: drop python-dotenv, unify config into config.toml"
```

---

### Task 9: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update setup section**

Change:
```
cp .env.example .env                                 # then add MORGEN_API_KEY
```
to:
```
cp config.toml.example config.toml                   # then add api_key (or run gm init)
```

**Step 2: Update Gotchas section**

Replace `.env` / `MORGEN_API_KEY` gotcha with:
```
- **`config.toml`** — XDG discovery: `$GM_CONFIG` → `./config.toml` → `~/.config/guten-morgen/config.toml`. Run `gm init` for first-time setup.
```

Replace `.config.toml` gotcha with:
```
- **Calendar groups** — configured in `config.toml` under `[groups.*]`. Use `--group all` to bypass filtering.
```

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for XDG config migration"
```
