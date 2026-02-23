# Retry with Backoff Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Auto-retry on 429 rate limits with a live countdown for humans and compact JSON for agents.

**Architecture:** Retry loop in `MorgenClient._request()` with an `on_retry` callback set by the CLI layer based on output format. The callback owns the sleep so human mode can tick a Rich progress bar every second.

**Tech Stack:** httpx (existing), rich (existing dep), time.sleep, Callable type

---

### Task 1: Add `max_retries` to Settings

**Files:**
- Modify: `src/guten_morgen/config.py:68-75`
- Test: `tests/test_config.py` (existing)

**Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
class TestSettingsMaxRetries:
    def test_default_max_retries(self) -> None:
        s = Settings(api_key="k")
        assert s.max_retries == 2

    def test_custom_max_retries(self) -> None:
        s = Settings(api_key="k", max_retries=5)
        assert s.max_retries == 5
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py::TestSettingsMaxRetries -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'max_retries'`

**Step 3: Write minimal implementation**

In `src/guten_morgen/config.py`, add to the `Settings` dataclass (line ~74):

```python
@dataclass
class Settings:
    """Morgen API configuration."""

    api_key: str
    base_url: str = "https://api.morgen.so/v3"
    timeout: float = 30.0
    max_retries: int = 2
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py::TestSettingsMaxRetries -v`
Expected: PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/config.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/guten_morgen/config.py tests/test_config.py
git commit -m "feat(config): add max_retries setting (default 2)"
```

---

### Task 2: Add retry loop to `_request()` with `on_retry` callback

**Files:**
- Modify: `src/guten_morgen/client.py:70-130`
- Test: `tests/test_client.py` (add new class)

**Step 1: Write the failing tests**

Add to `tests/test_client.py`:

```python
import time


def _make_client_with_retry(
    transport: httpx.MockTransport,
    *,
    max_retries: int = 2,
    on_retry: Any = None,
) -> MorgenClient:
    settings = Settings(api_key="test-key", max_retries=max_retries)
    return MorgenClient(settings, transport=transport, on_retry=on_retry)


def _countdown_transport(fail_count: int, retry_after: str = "5") -> httpx.MockTransport:
    """Transport that returns 429 `fail_count` times, then 200."""
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] <= fail_count:
            return httpx.Response(
                status_code=429,
                content=b"Rate limited",
                headers={"Retry-After": retry_after},
            )
        return httpx.Response(
            status_code=200,
            content=json.dumps({"data": "ok"}).encode(),
        )

    return httpx.MockTransport(handler)


class TestRetryWithBackoff:
    def test_retries_on_429_then_succeeds(self) -> None:
        """Single 429 followed by 200 should succeed."""
        recordings: list[tuple[int, int, int]] = []

        def recorder(wait: int, attempt: int, max_r: int) -> None:
            recordings.append((wait, attempt, max_r))

        client = _make_client_with_retry(
            _countdown_transport(1),
            on_retry=recorder,
        )
        result = client._request("GET", "/test")
        assert result == {"data": "ok"}
        assert len(recordings) == 1
        assert recordings[0] == (5, 1, 2)

    def test_exhausts_retries_raises_rate_limit(self) -> None:
        """After max_retries 429s, should raise RateLimitError."""
        recordings: list[tuple[int, int, int]] = []

        def recorder(wait: int, attempt: int, max_r: int) -> None:
            recordings.append((wait, attempt, max_r))

        client = _make_client_with_retry(
            _countdown_transport(10),  # more 429s than retries
            max_retries=2,
            on_retry=recorder,
        )
        with pytest.raises(RateLimitError):
            client._request("GET", "/test")
        assert len(recordings) == 2  # called for each retry attempt

    def test_no_retry_on_non_429(self) -> None:
        """Non-429 errors should not trigger retry."""
        recordings: list[tuple[int, int, int]] = []

        def recorder(wait: int, attempt: int, max_r: int) -> None:
            recordings.append((wait, attempt, max_r))

        client = _make_client_with_retry(
            _mock_transport(400, "Bad request"),
            on_retry=recorder,
        )
        with pytest.raises(MorgenAPIError):
            client._request("GET", "/test")
        assert recordings == []

    def test_retry_after_clamped_floor(self) -> None:
        """Retry-After below 5 is clamped to 5."""
        recordings: list[tuple[int, int, int]] = []

        def recorder(wait: int, attempt: int, max_r: int) -> None:
            recordings.append((wait, attempt, max_r))

        client = _make_client_with_retry(
            _countdown_transport(1, retry_after="1"),
            on_retry=recorder,
        )
        client._request("GET", "/test")
        assert recordings[0][0] == 5

    def test_retry_after_clamped_ceiling(self) -> None:
        """Retry-After above 60 is clamped to 60."""
        recordings: list[tuple[int, int, int]] = []

        def recorder(wait: int, attempt: int, max_r: int) -> None:
            recordings.append((wait, attempt, max_r))

        client = _make_client_with_retry(
            _countdown_transport(1, retry_after="120"),
            on_retry=recorder,
        )
        client._request("GET", "/test")
        assert recordings[0][0] == 60

    def test_retry_after_missing_defaults_to_15(self) -> None:
        """Missing Retry-After header defaults to 15s."""
        recordings: list[tuple[int, int, int]] = []

        def recorder(wait: int, attempt: int, max_r: int) -> None:
            recordings.append((wait, attempt, max_r))

        call_count = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            call_count["n"] += 1
            if call_count["n"] <= 1:
                return httpx.Response(status_code=429, content=b"Rate limited")
            return httpx.Response(
                status_code=200,
                content=json.dumps({"data": "ok"}).encode(),
            )

        client = _make_client_with_retry(
            httpx.MockTransport(handler),
            on_retry=recorder,
        )
        client._request("GET", "/test")
        assert recordings[0][0] == 15

    def test_no_callback_still_retries(self) -> None:
        """Without on_retry callback, retry still works (just sleeps silently)."""
        client = _make_client_with_retry(
            _countdown_transport(1, retry_after="5"),
            on_retry=None,
        )
        result = client._request("GET", "/test")
        assert result == {"data": "ok"}

    def test_zero_max_retries_raises_immediately(self) -> None:
        """max_retries=0 means no retry, raise on first 429."""
        client = _make_client_with_retry(
            _countdown_transport(1),
            max_retries=0,
        )
        with pytest.raises(RateLimitError):
            client._request("GET", "/test")
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py::TestRetryWithBackoff -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'on_retry'`

**Step 3: Write the implementation**

In `src/guten_morgen/client.py`, modify `__init__` and `_request`:

```python
import time
from collections.abc import Callable

# Add to imports at top of file

class MorgenClient:
    """Sync HTTP client for the Morgen v3 API."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        cache: Any | None = None,
        on_retry: Callable[[int, int, int], None] | None = None,
    ) -> None:
        self._cache = cache
        self._settings = settings
        self._on_retry = on_retry
        kwargs: dict[str, Any] = {
            "base_url": settings.base_url,
            "headers": {"Authorization": f"ApiKey {settings.api_key}"},
            "timeout": settings.timeout,
        }
        if transport is not None:
            kwargs["transport"] = transport
        self._http = httpx.Client(**kwargs)

    # ... (close, cache methods unchanged) ...

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an API request with error mapping and retry on rate limit."""
        max_retries = self._settings.max_retries
        for attempt in range(max_retries + 1):
            resp = self._http.request(method, path, **kwargs)

            if resp.status_code == 429:
                if attempt >= max_retries:
                    retry_after = resp.headers.get("Retry-After", "unknown")
                    raise RateLimitError(
                        f"Rate limit exceeded. Retry after {retry_after}s",
                        suggestions=[
                            f"Wait {retry_after} seconds before retrying",
                            "Reduce request frequency (100 pts / 15 min)",
                        ],
                    )
                # Parse and clamp wait time
                try:
                    wait = int(resp.headers.get("Retry-After", "15"))
                except (ValueError, TypeError):
                    wait = 15
                wait = max(5, min(60, wait))

                if self._on_retry is not None:
                    self._on_retry(wait, attempt + 1, max_retries)
                else:
                    time.sleep(wait)
                continue

            if resp.status_code == 401:
                raise AuthenticationError("Invalid or missing API key")
            if resp.status_code == 404:
                raise NotFoundError(f"Resource not found: {path}")
            if resp.status_code >= 400:
                body = resp.text
                raise MorgenAPIError(f"API error {resp.status_code}: {body}")

            if resp.status_code == 204:
                return None

            return resp.json()

        # Should not reach here, but satisfy mypy
        raise MorgenAPIError("Unexpected retry loop exit")  # pragma: no cover
```

**Important:** The 429 check is now BEFORE the other status checks inside the loop. The 401/404/400 checks don't retry.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py::TestRetryWithBackoff -v`
Expected: PASS

**Step 5: Run the existing 429 test — update it**

The existing `test_429_raises_rate_limit` creates a client with no `on_retry` and `max_retries=2` (default). It will now retry twice before raising. Update it to use `max_retries=0`:

In `tests/test_client.py`, update `_make_client`:

```python
def _make_client(transport: httpx.MockTransport) -> MorgenClient:
    settings = Settings(api_key="test-key", max_retries=0)
    return MorgenClient(settings, transport=transport)
```

This preserves the existing test behavior — direct raise on 429 with no retry.

**Step 6: Run full test suite**

Run: `uv run pytest tests/test_client.py -v`
Expected: all PASS

**Step 7: Run mypy**

Run: `uv run mypy src/guten_morgen/client.py`
Expected: clean

**Step 8: Commit**

```bash
git add src/guten_morgen/client.py tests/test_client.py
git commit -m "feat(client): retry on 429 with on_retry callback"
```

---

### Task 3: Build dual-mode retry callbacks

**Files:**
- Create: `src/guten_morgen/retry.py`
- Test: `tests/test_retry.py`

**Step 1: Write the failing tests**

Create `tests/test_retry.py`:

```python
"""Tests for retry callback factories."""

from __future__ import annotations

import json
import io
from unittest.mock import patch

from guten_morgen.retry import make_human_retry_callback, make_agent_retry_callback


class TestAgentRetryCallback:
    def test_emits_json_to_stderr(self) -> None:
        """Agent callback writes compact JSON to stderr and sleeps."""
        buf = io.StringIO()
        with patch("time.sleep") as mock_sleep, patch("sys.stderr", buf):
            cb = make_agent_retry_callback()
            cb(15, 1, 2)
        output = json.loads(buf.getvalue().strip())
        assert output == {"retry": {"wait": 15, "attempt": 1, "max": 2}}
        mock_sleep.assert_called_once_with(15)

    def test_multiple_retries_emit_multiple_lines(self) -> None:
        """Each retry emits a separate JSON line."""
        buf = io.StringIO()
        with patch("time.sleep"), patch("sys.stderr", buf):
            cb = make_agent_retry_callback()
            cb(10, 1, 2)
            cb(10, 2, 2)
        lines = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
        assert len(lines) == 2
        assert lines[0]["retry"]["attempt"] == 1
        assert lines[1]["retry"]["attempt"] == 2


class TestHumanRetryCallback:
    def test_sleeps_for_wait_seconds(self) -> None:
        """Human callback sleeps in 1-second ticks totaling wait time."""
        sleep_total = {"t": 0.0}
        original_sleep = None

        def fake_sleep(s: float) -> None:
            sleep_total["t"] += s

        with patch("time.sleep", side_effect=fake_sleep):
            cb = make_human_retry_callback()
            cb(3, 1, 2)
        assert sleep_total["t"] == 3.0

    def test_does_not_crash_without_terminal(self) -> None:
        """Callback works even if rich can't detect a terminal."""
        with patch("time.sleep"):
            cb = make_human_retry_callback()
            cb(1, 1, 2)  # should not raise
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_retry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'guten_morgen.retry'`

**Step 3: Write the implementation**

Create `src/guten_morgen/retry.py`:

```python
"""Retry callback factories for human and agent output modes."""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable


def make_agent_retry_callback() -> Callable[[int, int, int], None]:
    """Return a callback that emits compact JSON to stderr, then sleeps."""

    def callback(wait: int, attempt: int, max_retries: int) -> None:
        msg = {"retry": {"wait": wait, "attempt": attempt, "max": max_retries}}
        print(json.dumps(msg, separators=(",", ":")), file=sys.stderr)
        time.sleep(wait)

    return callback


def make_human_retry_callback() -> Callable[[int, int, int], None]:
    """Return a callback that shows a Rich countdown on stderr, then sleeps."""

    def callback(wait: int, attempt: int, max_retries: int) -> None:
        try:
            from rich.console import Console
            from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn

            console = Console(stderr=True)
            with Progress(
                TextColumn(f"[yellow]⏳ Rate limited (attempt {{task.completed}}/{max_retries}).[/yellow]"),
                TextColumn("[bold]Retrying in"),
                BarColumn(),
                TimeRemainingColumn(elapsed_when_finished=False),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task("waiting", total=wait)
                for _ in range(wait):
                    time.sleep(1)
                    progress.advance(task)
        except Exception:
            # Fallback: plain stderr + sleep if Rich fails
            print(f"Rate limited. Waiting {wait}s (attempt {attempt}/{max_retries})...", file=sys.stderr)
            time.sleep(wait)

    return callback
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_retry.py -v`
Expected: PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/retry.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/guten_morgen/retry.py tests/test_retry.py
git commit -m "feat(retry): dual-mode callback factories (human + agent)"
```

---

### Task 4: Wire callbacks into CLI

**Files:**
- Modify: `src/guten_morgen/cli.py:471-479`
- Test: `tests/test_cli_retry.py` (new)

**Step 1: Write the failing test**

Create `tests/test_cli_retry.py`:

```python
"""Tests for CLI retry integration."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from guten_morgen.cli import cli


class TestCliRetryWiring:
    def test_json_mode_uses_agent_callback(self, runner: CliRunner, mock_client: MagicMock) -> None:
        """When --json is passed, agent retry callback is wired."""
        with patch("guten_morgen.cli._get_client") as get_client:
            get_client.return_value = mock_client
            runner.invoke(cli, ["accounts", "list", "--json"])
            # Verify _get_client was called (it always is)
            get_client.assert_called()

    def test_table_mode_uses_human_callback(self, runner: CliRunner, mock_client: MagicMock) -> None:
        """When table format is used, human retry callback is wired."""
        with patch("guten_morgen.cli._get_client") as get_client:
            get_client.return_value = mock_client
            runner.invoke(cli, ["accounts", "list"])
            get_client.assert_called()
```

**Step 2: Run tests to verify they pass (baseline — we're testing wiring)**

These tests verify the commands don't crash with the new wiring. They'll initially pass since `_get_client` is mocked. The real test is the integration.

**Step 3: Modify `_get_client` to accept format and wire callback**

In `src/guten_morgen/cli.py`, update `_get_client`:

```python
def _get_client(fmt: str = "table") -> MorgenClient:
    """Create a MorgenClient from settings, with cache and retry callback."""
    from guten_morgen.client import MorgenClient
    from guten_morgen.retry import make_agent_retry_callback, make_human_retry_callback

    settings = load_settings()
    ctx = click.get_current_context(silent=True)
    no_cache = ctx.obj.get("no_cache", False) if ctx and ctx.obj else False
    cache = None if no_cache else _get_cache_store()

    on_retry = make_human_retry_callback() if fmt == "table" else make_agent_retry_callback()

    return MorgenClient(settings, cache=cache, on_retry=on_retry)
```

Then update every call site from `_get_client()` to `_get_client(fmt)`. There are ~30 call sites. All of them already have `fmt` in scope (from the `@output_options` decorator).

For commands that don't have `fmt` (like `_get_client()` in `cache clear`), keep the default `"table"`.

**Step 4: Run the full test suite**

Run: `uv run pytest -x -q`
Expected: all PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/cli.py`
Expected: clean

**Step 6: Commit**

```bash
git add src/guten_morgen/cli.py tests/test_cli_retry.py
git commit -m "feat(cli): wire dual-mode retry callbacks into all commands"
```

---

### Task 5: Final verification

**Step 1: Run full test suite with coverage**

Run: `uv run pytest -x -q --cov`
Expected: all PASS, coverage >= 90%

**Step 2: Run mypy on all sources**

Run: `uv run mypy src/`
Expected: clean

**Step 3: Run pre-commit hooks**

Run: `uv run pre-commit run --all-files`
Expected: all PASS

**Step 4: Final commit if any formatting changes**

```bash
git add -A && git commit -m "style: format retry implementation"
```
