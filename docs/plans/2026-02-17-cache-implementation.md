# Cache Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add file-based TTL caching to the Morgen CLI to reduce API calls and avoid rate limits.

**Architecture:** A `CacheStore` class persists JSON responses to `~/.cache/morgen/` with per-resource TTLs. `MorgenClient` gains an optional `cache` parameter — list/get methods check cache first, write methods invalidate. CLI adds `--no-cache` flag and `morgen cache clear|stats` commands.

**Tech Stack:** Python stdlib only (json, time, pathlib, hashlib). No new dependencies.

**Design doc:** `docs/plans/2026-02-17-cache-design.md`

---

### Task 1: CacheStore — Basic get/set with TTL

**Files:**
- Create: `src/morgen/cache.py`
- Test: `tests/test_cache.py`

**Step 1: Write the failing tests**

```python
"""Tests for CacheStore."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from morgen.cache import CacheStore


class TestCacheGetSet:
    def test_set_and_get_returns_data(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "acc-1"}], ttl=3600)
        result = store.get("accounts")
        assert result == [{"id": "acc-1"}]

    def test_get_missing_key_returns_none(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        assert store.get("nonexistent") is None

    def test_expired_entry_returns_none(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "acc-1"}], ttl=0)
        # TTL=0 means already expired
        time.sleep(0.01)
        assert store.get("accounts") is None

    def test_nested_key_with_slashes(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("events/abc123", [{"id": "evt-1"}], ttl=3600)
        result = store.get("events/abc123")
        assert result == [{"id": "evt-1"}]

    def test_overwrite_existing_key(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "old"}], ttl=3600)
        store.set("accounts", [{"id": "new"}], ttl=3600)
        assert store.get("accounts") == [{"id": "new"}]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'morgen.cache'`

**Step 3: Write minimal implementation**

```python
"""File-based TTL cache for Morgen API responses."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

# TTL constants (seconds)
TTL_ACCOUNTS = 86400   # 24 hours
TTL_CALENDARS = 86400  # 24 hours
TTL_TAGS = 14400       # 4 hours
TTL_EVENTS = 1800      # 30 minutes
TTL_TASKS = 1800       # 30 minutes
TTL_SINGLE = 300       # 5 minutes (get by ID)

_DEFAULT_CACHE_DIR = Path.home() / ".cache" / "morgen"


class CacheStore:
    """File-based TTL cache for API responses."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._dir = cache_dir or _DEFAULT_CACHE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._meta_path = self._dir / "_meta.json"
        self._meta: dict[str, dict[str, float]] = self._load_meta()

    def _load_meta(self) -> dict[str, dict[str, float]]:
        try:
            return json.loads(self._meta_path.read_text())  # type: ignore[no-any-return]
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_meta(self) -> None:
        self._meta_path.write_text(json.dumps(self._meta))

    def _data_path(self, key: str) -> Path:
        # Replace / with -- for flat file names
        safe = key.replace("/", "--")
        return self._dir / f"{safe}.json"

    def get(self, key: str) -> Any | None:
        """Return cached data if fresh, else None."""
        entry = self._meta.get(key)
        if entry is None:
            return None
        if time.time() > entry["ts"] + entry["ttl"]:
            return None
        path = self._data_path(key)
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def set(self, key: str, data: Any, ttl: int) -> None:
        """Cache data with a TTL in seconds."""
        path = self._data_path(key)
        path.write_text(json.dumps(data, default=str, ensure_ascii=False))
        self._meta[key] = {"ts": time.time(), "ttl": float(ttl)}
        self._save_meta()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cache.py -v`
Expected: All 5 PASS

**Step 5: Commit**

```bash
git add src/morgen/cache.py tests/test_cache.py
git commit -m "feat(cache): add CacheStore with get/set and TTL expiry"
```

---

### Task 2: CacheStore — invalidate and clear

**Files:**
- Modify: `src/morgen/cache.py`
- Modify: `tests/test_cache.py`

**Step 1: Write the failing tests**

Append to `tests/test_cache.py`:

```python
class TestCacheInvalidate:
    def test_invalidate_removes_matching_keys(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("tasks/list", [{"id": "t1"}], ttl=3600)
        store.set("tasks/abc", {"id": "t1"}, ttl=3600)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        store.invalidate("tasks")
        assert store.get("tasks/list") is None
        assert store.get("tasks/abc") is None
        assert store.get("accounts") == [{"id": "a1"}]

    def test_invalidate_nonexistent_prefix_is_noop(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        store.invalidate("tasks")  # no tasks cached
        assert store.get("accounts") == [{"id": "a1"}]


class TestCacheClear:
    def test_clear_removes_all(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        store.set("tasks/list", [{"id": "t1"}], ttl=3600)
        store.clear()
        assert store.get("accounts") is None
        assert store.get("tasks/list") is None
```

**Step 2: Run tests to verify new tests fail**

Run: `uv run pytest tests/test_cache.py::TestCacheInvalidate -v`
Expected: FAIL — `AttributeError: 'CacheStore' object has no attribute 'invalidate'`

**Step 3: Add invalidate and clear to CacheStore**

Add to `CacheStore` class in `src/morgen/cache.py`:

```python
    def invalidate(self, prefix: str) -> None:
        """Remove all cache entries whose key starts with prefix."""
        to_remove = [k for k in self._meta if k == prefix or k.startswith(prefix + "/")]
        for key in to_remove:
            self._data_path(key).unlink(missing_ok=True)
            del self._meta[key]
        if to_remove:
            self._save_meta()

    def clear(self) -> None:
        """Wipe all cached data."""
        for key in list(self._meta):
            self._data_path(key).unlink(missing_ok=True)
        self._meta.clear()
        self._save_meta()
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cache.py -v`
Expected: All 8 PASS

**Step 5: Commit**

```bash
git add src/morgen/cache.py tests/test_cache.py
git commit -m "feat(cache): add invalidate by prefix and clear"
```

---

### Task 3: CacheStore — stats

**Files:**
- Modify: `src/morgen/cache.py`
- Modify: `tests/test_cache.py`

**Step 1: Write the failing test**

Append to `tests/test_cache.py`:

```python
class TestCacheStats:
    def test_stats_shows_entries(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=86400)
        store.set("tasks/list", [{"id": "t1"}], ttl=1800)
        stats = store.stats()
        assert stats["entries"] == 2
        assert "accounts" in stats["keys"]
        assert "tasks/list" in stats["keys"]

    def test_stats_empty_cache(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        stats = store.stats()
        assert stats["entries"] == 0
        assert stats["keys"] == {}
```

**Step 2: Run to verify fail**

Run: `uv run pytest tests/test_cache.py::TestCacheStats -v`
Expected: FAIL — `AttributeError: 'CacheStore' object has no attribute 'stats'`

**Step 3: Add stats method**

Add to `CacheStore` class in `src/morgen/cache.py`:

```python
    def stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        now = time.time()
        keys: dict[str, dict[str, Any]] = {}
        for key, entry in self._meta.items():
            age = now - entry["ts"]
            remaining = entry["ttl"] - age
            path = self._data_path(key)
            size = path.stat().st_size if path.exists() else 0
            keys[key] = {
                "age_seconds": round(age, 1),
                "ttl": int(entry["ttl"]),
                "remaining_seconds": round(max(0, remaining), 1),
                "expired": remaining <= 0,
                "size_bytes": size,
            }
        return {"entries": len(keys), "cache_dir": str(self._dir), "keys": keys}
```

**Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_cache.py -v`
Expected: All 10 PASS

**Step 5: Commit**

```bash
git add src/morgen/cache.py tests/test_cache.py
git commit -m "feat(cache): add stats method"
```

---

### Task 4: CacheStore — resilience (corrupt files, errors)

**Files:**
- Modify: `tests/test_cache.py`

**Step 1: Write the failing tests**

Append to `tests/test_cache.py`:

```python
class TestCacheResilience:
    def test_corrupt_data_file_returns_none(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        # Corrupt the data file
        store._data_path("accounts").write_text("not json{{{")
        assert store.get("accounts") is None

    def test_corrupt_meta_file_starts_fresh(self, tmp_path: Path) -> None:
        (tmp_path / "_meta.json").write_text("not json{{{")
        store = CacheStore(cache_dir=tmp_path)
        assert store.get("anything") is None

    def test_missing_data_file_returns_none(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        # Remove the data file but leave meta
        store._data_path("accounts").unlink()
        assert store.get("accounts") is None
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_cache.py::TestCacheResilience -v`
Expected: All 3 PASS (these should already work given existing error handling)

**Step 3: If any fail, fix the error handling in cache.py**

The existing try/except in `get()` and `_load_meta()` should handle these. If not, add appropriate guards.

**Step 4: Commit (if any changes were needed)**

```bash
git add tests/test_cache.py
git commit -m "test(cache): add resilience tests for corrupt/missing files"
```

---

### Task 5: Integrate cache into MorgenClient

**Files:**
- Modify: `src/morgen/client.py:57-70` (MorgenClient.__init__)
- Modify: `src/morgen/client.py:100-224` (all list/get/write methods)
- Test: `tests/test_client_cache.py` (new file)

**Step 1: Write the failing tests**

Create `tests/test_client_cache.py`:

```python
"""Tests for MorgenClient cache integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from morgen.cache import CacheStore
from morgen.client import MorgenClient
from morgen.config import Settings
from tests.conftest import mock_transport_handler


def _make_client(tmp_path: Path) -> tuple[MorgenClient, CacheStore]:
    """Create a cached MorgenClient with mock transport."""
    cache = CacheStore(cache_dir=tmp_path)
    settings = Settings(api_key="test-key")
    transport = httpx.MockTransport(mock_transport_handler)
    client = MorgenClient(settings, transport=transport, cache=cache)
    return client, cache


class TestCachedListAccounts:
    def test_first_call_hits_api_and_caches(self, tmp_path: Path) -> None:
        client, cache = _make_client(tmp_path)
        result = client.list_accounts()
        assert len(result) == 2
        assert cache.get("accounts") is not None

    def test_second_call_returns_cached(self, tmp_path: Path) -> None:
        client, cache = _make_client(tmp_path)
        result1 = client.list_accounts()
        # Overwrite cache with different data to prove second call uses cache
        cache.set("accounts", [{"id": "cached-acc"}], ttl=3600)
        result2 = client.list_accounts()
        assert result2 == [{"id": "cached-acc"}]


class TestCachedListTasks:
    def test_caches_tasks_list(self, tmp_path: Path) -> None:
        client, cache = _make_client(tmp_path)
        client.list_tasks()
        assert cache.get("tasks/list") is not None


class TestCachedGetTask:
    def test_caches_single_task(self, tmp_path: Path) -> None:
        client, cache = _make_client(tmp_path)
        client.get_task("task-1")
        assert cache.get("tasks/task-1") is not None


class TestCacheInvalidationOnWrite:
    def test_create_task_invalidates_tasks_cache(self, tmp_path: Path) -> None:
        client, cache = _make_client(tmp_path)
        client.list_tasks()
        assert cache.get("tasks/list") is not None
        client.create_task({"title": "New"})
        assert cache.get("tasks/list") is None

    def test_delete_task_invalidates_tasks_cache(self, tmp_path: Path) -> None:
        client, cache = _make_client(tmp_path)
        client.list_tasks()
        assert cache.get("tasks/list") is not None
        client.delete_task("task-1")
        assert cache.get("tasks/list") is None

    def test_create_event_invalidates_events_cache(self, tmp_path: Path) -> None:
        client, cache = _make_client(tmp_path)
        client.list_events("acc-1", ["cal-1"], "2026-01-01", "2026-01-02")
        # Some events key should exist
        events_keys = [k for k in cache._meta if k.startswith("events")]
        assert len(events_keys) > 0
        client.create_event({"title": "New", "accountId": "acc-1", "calendarId": "cal-1"})
        events_keys = [k for k in cache._meta if k.startswith("events")]
        assert len(events_keys) == 0

    def test_create_tag_invalidates_tags_cache(self, tmp_path: Path) -> None:
        client, cache = _make_client(tmp_path)
        client.list_tags()
        assert cache.get("tags") is not None
        client.create_tag({"name": "test"})
        assert cache.get("tags") is None


class TestNoCacheStillWorks:
    def test_client_without_cache(self, tmp_path: Path) -> None:
        """Existing behavior: cache=None works fine."""
        settings = Settings(api_key="test-key")
        transport = httpx.MockTransport(mock_transport_handler)
        client = MorgenClient(settings, transport=transport)
        result = client.list_accounts()
        assert len(result) == 2
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client_cache.py -v`
Expected: FAIL — `TypeError: MorgenClient.__init__() got an unexpected keyword argument 'cache'`

**Step 3: Modify MorgenClient to accept and use cache**

In `src/morgen/client.py`, modify the class:

1. Update `__init__` (line 60) to accept `cache`:

```python
    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        cache: Any | None = None,
    ) -> None:
        self._settings = settings
        self._cache = cache
        kwargs: dict[str, Any] = {
            "base_url": settings.base_url,
            "headers": {"Authorization": f"ApiKey {settings.api_key}"},
            "timeout": settings.timeout,
        }
        if transport is not None:
            kwargs["transport"] = transport
        self._http = httpx.Client(**kwargs)
```

2. Add import at top: `import hashlib`

3. Add cache helper:

```python
    def _cache_get(self, key: str) -> Any | None:
        if self._cache is not None:
            return self._cache.get(key)
        return None

    def _cache_set(self, key: str, data: Any, ttl: int) -> None:
        if self._cache is not None:
            self._cache.set(key, data, ttl)

    def _cache_invalidate(self, prefix: str) -> None:
        if self._cache is not None:
            self._cache.invalidate(prefix)
```

4. Update every list/get method to check cache first, then store. Update every write method to invalidate. Import TTL constants from cache module:

```python
from morgen.cache import (
    TTL_ACCOUNTS,
    TTL_CALENDARS,
    TTL_EVENTS,
    TTL_SINGLE,
    TTL_TAGS,
    TTL_TASKS,
)
```

Example pattern for list methods:

```python
    def list_accounts(self) -> list[dict[str, Any]]:
        cached = self._cache_get("accounts")
        if cached is not None:
            return cached
        data = self._request("GET", "/integrations/accounts/list")
        result = _extract_list(data, "accounts")
        self._cache_set("accounts", result, TTL_ACCOUNTS)
        return result
```

Example pattern for get methods:

```python
    def get_task(self, task_id: str) -> dict[str, Any]:
        key = f"tasks/{task_id}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        data = self._request("GET", "/tasks/", params={"id": task_id})
        result = _extract_single(data, "task")
        self._cache_set(key, result, TTL_SINGLE)
        return result
```

Example pattern for events list (hashed key):

```python
    def list_events(self, account_id: str, calendar_ids: list[str], start: str, end: str) -> list[dict[str, Any]]:
        raw = f"{account_id}:{','.join(sorted(calendar_ids))}:{start}:{end}"
        key = f"events/{hashlib.md5(raw.encode()).hexdigest()[:12]}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        data = self._request("GET", "/events/list", params={...})
        result = _extract_list(data, "events")
        self._cache_set(key, result, TTL_EVENTS)
        return result
```

Example pattern for write methods:

```python
    def create_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", "/tasks/create", json=task_data)
        self._cache_invalidate("tasks")
        return _extract_single(data, "task")
```

Full list of methods to update:

| Method | Cache key | TTL | Invalidates |
|--------|-----------|-----|-------------|
| `list_accounts` | `accounts` | TTL_ACCOUNTS | — |
| `list_calendars` | `calendars` | TTL_CALENDARS | — |
| `list_events` | `events/<md5>` | TTL_EVENTS | — |
| `list_tasks` | `tasks/list` | TTL_TASKS | — |
| `list_tags` | `tags` | TTL_TAGS | — |
| `get_task` | `tasks/<id>` | TTL_SINGLE | — |
| `get_tag` | `tags/<id>` | TTL_SINGLE | — |
| `create_event` | — | — | `events` |
| `update_event` | — | — | `events` |
| `delete_event` | — | — | `events` |
| `create_task` | — | — | `tasks` |
| `update_task` | — | — | `tasks` |
| `close_task` | — | — | `tasks` |
| `reopen_task` | — | — | `tasks` |
| `move_task` | — | — | `tasks` |
| `delete_task` | — | — | `tasks` |
| `create_tag` | — | — | `tags` |
| `update_tag` | — | — | `tags` |
| `delete_tag` | — | — | `tags` |

**Step 4: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS (old tests use `cache=None` by default, new tests verify cache behavior)

**Step 5: Run mypy and ruff**

Run: `uv run mypy src/ && uv run ruff check .`
Expected: Clean

**Step 6: Commit**

```bash
git add src/morgen/client.py tests/test_client_cache.py
git commit -m "feat(cache): integrate CacheStore into MorgenClient"
```

---

### Task 6: CLI --no-cache flag and cache commands

**Files:**
- Modify: `src/morgen/cli.py:79-82` (cli group)
- Modify: `src/morgen/cli.py:183-188` (_get_client)
- Add new commands to `src/morgen/cli.py`
- Test: `tests/test_cli_cache.py` (new file)

**Step 1: Write the failing tests**

Create `tests/test_cli_cache.py`:

```python
"""Tests for cache CLI commands and --no-cache flag."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from morgen.cache import CacheStore
from morgen.cli import cli
from morgen.client import MorgenClient


class TestCacheClearCommand:
    def test_cache_clear(self, runner: CliRunner, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        with patch("morgen.cli._get_cache_store", return_value=store):
            result = runner.invoke(cli, ["cache", "clear"])
        assert result.exit_code == 0
        assert store.get("accounts") is None


class TestCacheStatsCommand:
    def test_cache_stats_json(self, runner: CliRunner, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        with patch("morgen.cli._get_cache_store", return_value=store):
            result = runner.invoke(cli, ["cache", "stats"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["entries"] == 1


class TestNoCacheFlag:
    def test_no_cache_flag_exists(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["--no-cache", "accounts", "--json"])
        assert result.exit_code == 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli_cache.py -v`
Expected: FAIL

**Step 3: Modify cli.py**

1. Update the `cli` group to accept `--no-cache` and store in context:

```python
@click.group()
@click.option("--no-cache", is_flag=True, help="Bypass cache, fetch fresh from API.")
@click.pass_context
def cli(ctx: click.Context, no_cache: bool) -> None:
    """Morgen CLI — calendar and task management for Control Tower."""
    ctx.ensure_object(dict)
    ctx.obj["no_cache"] = no_cache
```

2. Add `_get_cache_store()` helper and update `_get_client()`:

```python
def _get_cache_store() -> CacheStore:
    from morgen.cache import CacheStore
    return CacheStore()

def _get_client(no_cache: bool = False) -> MorgenClient:
    from morgen.client import MorgenClient
    settings = load_settings()
    cache = None if no_cache else _get_cache_store()
    return MorgenClient(settings, cache=cache)
```

3. Update every command that calls `_get_client()` to pass context. Two approaches:
   - **Simple:** Use `click.get_current_context()` inside `_get_client()` to read no_cache:

```python
def _get_client() -> MorgenClient:
    from morgen.client import MorgenClient
    settings = load_settings()
    ctx = click.get_current_context(silent=True)
    no_cache = ctx.obj.get("no_cache", False) if ctx and ctx.obj else False
    cache = None if no_cache else _get_cache_store()
    return MorgenClient(settings, cache=cache)
```

   This approach requires NO changes to individual commands.

4. Add `cache` subgroup with `clear` and `stats`:

```python
@cli.group()
def cache() -> None:
    """Manage the local API cache."""

@cache.command("clear")
def cache_clear() -> None:
    """Wipe all cached API data."""
    store = _get_cache_store()
    store.clear()
    click.echo(json.dumps({"status": "cleared", "cache_dir": str(store._dir)}))

@cache.command("stats")
def cache_stats() -> None:
    """Show cache statistics."""
    store = _get_cache_store()
    click.echo(json.dumps(store.stats(), indent=2, default=str))
```

**Step 4: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

**Step 5: Run mypy and ruff**

Run: `uv run mypy src/ && uv run ruff check .`
Expected: Clean

**Step 6: Commit**

```bash
git add src/morgen/cli.py tests/test_cli_cache.py
git commit -m "feat(cache): add --no-cache flag and cache clear/stats commands"
```

---

### Task 7: Update usage text and run full verification

**Files:**
- Modify: `src/morgen/cli.py` (usage command text, lines 92-179)
- Modify: `tests/test_cli_usage.py` (if it checks for specific text)

**Step 1: Update usage text**

Add to the usage command output, after "## Global Options":

```
- `--no-cache` (bypass cache, fetch fresh from API)

### Cache Management
- `morgen cache clear`
  Wipe all cached API data.

- `morgen cache stats`
  Show cache ages, TTLs, and sizes.
```

**Step 2: Run full verification suite**

```bash
uv run pytest tests/ -v
uv run mypy src/
uv run ruff check .
uv run pre-commit run --all-files
```

Expected: All pass.

**Step 3: Commit**

```bash
git add src/morgen/cli.py tests/test_cli_usage.py
git commit -m "docs: update usage text with cache commands"
```

---

### Task 8: E2E smoke test with real API

**No code changes — verification only.**

```bash
# First call — should hit API (cold cache)
uv run morgen today --json --response-format concise

# Second call — should be instant (warm cache)
uv run morgen today --json --response-format concise

# Check cache stats
uv run morgen cache stats

# Bypass cache
uv run morgen --no-cache accounts --json

# Create a task (should invalidate tasks cache)
uv run morgen tasks create --title "cache test"

# Verify tasks cache was invalidated
uv run morgen cache stats

# Clean up
uv run morgen cache clear
```

Expected: Second `today` call is instant (no API hit). Stats show cached entries. After create, tasks cache is gone.

**Commit (if any fixes needed):**

```bash
git commit -am "fix: E2E cache fixes"
```
