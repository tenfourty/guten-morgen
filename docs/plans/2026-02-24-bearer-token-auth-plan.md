# Bearer Token Auth — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add bearer token auth from the Morgen desktop app to get 50x more effective API capacity, with graceful fallback to API key.

**Architecture:** New `auth.py` module reads refresh token from Morgen desktop config, exchanges it for a 1-hour access token via `/identity/refresh`, and caches it. `Settings` gains an optional `bearer_token` field. `MorgenClient` uses `Bearer` header when available, falls back to `ApiKey`.

**Tech Stack:** Python 3.10+, httpx, Pydantic v2, pytest, mypy strict

**Design doc:** `docs/plans/2026-02-24-bearer-token-auth-design.md`

---

### Task 1: Create `auth.py` — Morgen Desktop Config Reader

**Files:**
- Create: `src/guten_morgen/auth.py`
- Create: `tests/test_auth.py`

**Step 1: Write the failing tests**

```python
"""Tests for bearer token auth."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from guten_morgen.auth import find_morgen_desktop_config, read_morgen_credentials


class TestFindMorgenDesktopConfig:
    def test_macos_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Finds config at ~/Library/Application Support/Morgen/config.json on macOS."""
        config_dir = tmp_path / "Library" / "Application Support" / "Morgen"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text('{"morgen-refresh-token": "tok", "morgen-device-id": "dev"}')
        monkeypatch.setenv("HOME", str(tmp_path))
        result = find_morgen_desktop_config()
        assert result == config_file

    def test_xdg_linux_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Finds config at $XDG_CONFIG_HOME/Morgen/config.json on Linux."""
        config_dir = tmp_path / "xdg" / "Morgen"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text('{"morgen-refresh-token": "tok", "morgen-device-id": "dev"}')
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        # Ensure macOS path doesn't exist
        monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
        result = find_morgen_desktop_config()
        assert result == config_file

    def test_not_installed_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when Morgen desktop is not installed."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert find_morgen_desktop_config() is None


class TestReadMorgenCredentials:
    def test_reads_refresh_token_and_device_id(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "morgen-refresh-token": "my-refresh-token",
            "morgen-device-id": "my-device-id",
        }))
        creds = read_morgen_credentials(config_file)
        assert creds is not None
        assert creds == ("my-refresh-token", "my-device-id")

    def test_missing_refresh_token_returns_none(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"morgen-device-id": "dev"}))
        assert read_morgen_credentials(config_file) is None

    def test_missing_device_id_returns_none(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"morgen-refresh-token": "tok"}))
        assert read_morgen_credentials(config_file) is None

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text("not json {{{")
        assert read_morgen_credentials(config_file) is None

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert read_morgen_credentials(tmp_path / "nope.json") is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL — `ImportError: cannot import name 'find_morgen_desktop_config' from 'guten_morgen.auth'`

**Step 3: Write minimal implementation**

```python
"""Bearer token auth via Morgen desktop app."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def find_morgen_desktop_config() -> Path | None:
    """Locate the Morgen desktop app config.json.

    Search order:
    1. macOS: ~/Library/Application Support/Morgen/config.json
    2. Linux/XDG: $XDG_CONFIG_HOME/Morgen/config.json (or ~/.config/Morgen/)
    """
    home = Path(os.environ.get("HOME", Path.home()))

    # macOS
    mac_path = home / "Library" / "Application Support" / "Morgen" / "config.json"
    if mac_path.is_file():
        return mac_path

    # Linux / XDG
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_home:
        xdg_path = Path(xdg_home) / "Morgen" / "config.json"
    else:
        xdg_path = home / ".config" / "Morgen" / "config.json"
    if xdg_path.is_file():
        return xdg_path

    return None


def read_morgen_credentials(config_path: Path) -> tuple[str, str] | None:
    """Read refresh token and device ID from Morgen desktop config.

    Returns (refresh_token, device_id) or None on any failure.
    """
    try:
        data = json.loads(config_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

    refresh_token = data.get("morgen-refresh-token")
    device_id = data.get("morgen-device-id")

    if not refresh_token or not device_id:
        return None

    return (str(refresh_token), str(device_id))
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_auth.py -v`
Expected: all PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/auth.py`
Expected: Success

**Step 6: Commit**

```bash
git add src/guten_morgen/auth.py tests/test_auth.py
git commit -m "feat(auth): add Morgen desktop config reader"
```

---

### Task 2: Add Token Refresh + Caching to `auth.py`

**Files:**
- Modify: `src/guten_morgen/auth.py`
- Modify: `tests/test_auth.py`

**Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
from unittest.mock import patch, MagicMock

from guten_morgen.auth import get_bearer_token, _refresh_access_token, _load_cached_token, _save_cached_token


class TestRefreshAccessToken:
    def test_successful_refresh(self) -> None:
        """POST to /identity/refresh returns an access token."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "token": "fresh-access-token",
            "expiresIn": 3600,
        }
        with patch("guten_morgen.auth.httpx.post", return_value=mock_response) as mock_post:
            result = _refresh_access_token("refresh-tok", "device-123")
        assert result is not None
        token, expires_at = result
        assert token == "fresh-access-token"
        assert expires_at > time.time()
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["refreshToken"] == "refresh-tok"
        assert call_kwargs[1]["json"]["deviceId"] == "device-123"

    def test_http_error_returns_none(self) -> None:
        """Non-200 response returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        with patch("guten_morgen.auth.httpx.post", return_value=mock_response):
            assert _refresh_access_token("bad-tok", "dev") is None

    def test_network_error_returns_none(self) -> None:
        """Network exception returns None."""
        with patch("guten_morgen.auth.httpx.post", side_effect=Exception("timeout")):
            assert _refresh_access_token("tok", "dev") is None


class TestTokenCache:
    def test_save_and_load(self, tmp_path: Path) -> None:
        """Saved token can be loaded back."""
        _save_cached_token(tmp_path, "my-token", time.time() + 3600)
        result = _load_cached_token(tmp_path)
        assert result is not None
        assert result[0] == "my-token"

    def test_expired_token_returns_none(self, tmp_path: Path) -> None:
        """Expired cached token is not returned."""
        _save_cached_token(tmp_path, "old-token", time.time() - 10)
        assert _load_cached_token(tmp_path) is None

    def test_missing_cache_returns_none(self, tmp_path: Path) -> None:
        """Missing cache file returns None."""
        assert _load_cached_token(tmp_path) is None

    def test_corrupt_cache_returns_none(self, tmp_path: Path) -> None:
        """Corrupt cache file returns None."""
        cache_file = tmp_path / "_bearer.json"
        cache_file.write_text("not json")
        assert _load_cached_token(tmp_path) is None


class TestGetBearerToken:
    def test_returns_cached_token(self, tmp_path: Path) -> None:
        """Returns cached token when it's still valid."""
        _save_cached_token(tmp_path, "cached-token", time.time() + 3600)
        with patch("guten_morgen.auth.find_morgen_desktop_config", return_value=None):
            result = get_bearer_token(tmp_path)
        assert result == "cached-token"

    def test_refreshes_expired_token(self, tmp_path: Path) -> None:
        """Refreshes when cached token is expired."""
        config_file = tmp_path / "morgen-config.json"
        config_file.write_text(json.dumps({
            "morgen-refresh-token": "refresh-tok",
            "morgen-device-id": "device-123",
        }))
        with (
            patch("guten_morgen.auth.find_morgen_desktop_config", return_value=config_file),
            patch(
                "guten_morgen.auth._refresh_access_token",
                return_value=("new-token", time.time() + 3600),
            ),
        ):
            result = get_bearer_token(tmp_path)
        assert result == "new-token"

    def test_no_desktop_app_returns_none(self, tmp_path: Path) -> None:
        """Returns None when desktop app is not installed."""
        with patch("guten_morgen.auth.find_morgen_desktop_config", return_value=None):
            assert get_bearer_token(tmp_path) is None

    def test_refresh_failure_returns_none(self, tmp_path: Path) -> None:
        """Returns None when token refresh fails."""
        config_file = tmp_path / "morgen-config.json"
        config_file.write_text(json.dumps({
            "morgen-refresh-token": "refresh-tok",
            "morgen-device-id": "device-123",
        }))
        with (
            patch("guten_morgen.auth.find_morgen_desktop_config", return_value=config_file),
            patch("guten_morgen.auth._refresh_access_token", return_value=None),
        ):
            assert get_bearer_token(tmp_path) is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL — `ImportError: cannot import name '_refresh_access_token'`

**Step 3: Write the implementation**

Add to `src/guten_morgen/auth.py`:

```python
import time

import httpx

_REFRESH_URL = "https://api.morgen.so/identity/refresh"
_BEARER_CACHE_FILE = "_bearer.json"
_EXPIRY_MARGIN = 300  # refresh 5 minutes before expiry


def _refresh_access_token(refresh_token: str, device_id: str) -> tuple[str, float] | None:
    """Exchange refresh token for a short-lived access token.

    Returns (access_token, expires_at_unix) or None on failure.
    """
    try:
        resp = httpx.post(
            _REFRESH_URL,
            json={"refreshToken": refresh_token, "deviceId": device_id},
            timeout=10.0,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        token = data.get("token")
        expires_in = data.get("expiresIn", 3600)
        if not token:
            return None
        return (str(token), time.time() + float(expires_in))
    except Exception:
        return None


def _load_cached_token(cache_dir: Path) -> tuple[str, float] | None:
    """Load bearer token from cache if still valid."""
    cache_file = cache_dir / _BEARER_CACHE_FILE
    try:
        data = json.loads(cache_file.read_text())
        token = data["token"]
        expires_at = float(data["expires_at"])
        if time.time() + _EXPIRY_MARGIN >= expires_at:
            return None
        return (str(token), expires_at)
    except (FileNotFoundError, json.JSONDecodeError, KeyError, OSError, ValueError):
        return None


def _save_cached_token(cache_dir: Path, token: str, expires_at: float) -> None:
    """Save bearer token to cache."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / _BEARER_CACHE_FILE
    cache_file.write_text(json.dumps({"token": token, "expires_at": expires_at}))


def get_bearer_token(cache_dir: Path) -> str | None:
    """Get a valid bearer token, using cache or refreshing as needed.

    Returns an access token string, or None if bearer auth is unavailable.
    All failures are silent — caller falls back to API key auth.
    """
    # 1. Try cache
    cached = _load_cached_token(cache_dir)
    if cached is not None:
        return cached[0]

    # 2. Find desktop app config
    config_path = find_morgen_desktop_config()
    if config_path is None:
        return None

    # 3. Read credentials
    creds = read_morgen_credentials(config_path)
    if creds is None:
        return None

    # 4. Refresh
    refresh_token, device_id = creds
    result = _refresh_access_token(refresh_token, device_id)
    if result is None:
        return None

    # 5. Cache and return
    access_token, expires_at = result
    _save_cached_token(cache_dir, access_token, expires_at)
    return access_token
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_auth.py -v`
Expected: all PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/auth.py`
Expected: Success

**Step 6: Commit**

```bash
git add src/guten_morgen/auth.py tests/test_auth.py
git commit -m "feat(auth): add token refresh and caching"
```

---

### Task 3: Wire Bearer Token into `Settings`

**Files:**
- Modify: `src/guten_morgen/config.py`
- Modify: `tests/test_config.py`

**Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
from unittest.mock import patch


class TestBearerTokenInSettings:
    def test_settings_has_bearer_token_field(self) -> None:
        s = Settings(api_key="test-key")
        assert s.bearer_token is None

    def test_settings_accepts_bearer_token(self) -> None:
        s = Settings(api_key="test-key", bearer_token="my-bearer")
        assert s.bearer_token == "my-bearer"

    def test_load_settings_populates_bearer_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MORGEN_API_KEY", "test-key")
        with patch("guten_morgen.config.get_bearer_token", return_value="desktop-token"):
            settings = load_settings()
        assert settings.bearer_token == "desktop-token"
        assert settings.api_key == "test-key"

    def test_load_settings_bearer_none_when_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MORGEN_API_KEY", "test-key")
        with patch("guten_morgen.config.get_bearer_token", return_value=None):
            settings = load_settings()
        assert settings.bearer_token is None

    def test_morgen_bearer_token_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """$MORGEN_BEARER_TOKEN env var overrides desktop app token."""
        monkeypatch.setenv("MORGEN_API_KEY", "test-key")
        monkeypatch.setenv("MORGEN_BEARER_TOKEN", "env-bearer")
        with patch("guten_morgen.config.get_bearer_token", return_value="desktop-token"):
            settings = load_settings()
        assert settings.bearer_token == "env-bearer"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py::TestBearerTokenInSettings -v`
Expected: FAIL — `TypeError: Settings.__init__() got an unexpected keyword argument 'bearer_token'`

**Step 3: Modify `config.py`**

Add field to `Settings` dataclass:

```python
@dataclass
class Settings:
    """Morgen API configuration."""

    api_key: str
    base_url: str = "https://api.morgen.so/v3"
    timeout: float = 30.0
    max_retries: int = 2
    bearer_token: str | None = None
```

Update `load_settings()` — add bearer token resolution after the api_key block:

```python
def load_settings() -> Settings:
    """Load settings from env vars and/or config TOML.

    API key priority: $MORGEN_API_KEY env var > api_key in config TOML.
    Bearer token priority: $MORGEN_BEARER_TOKEN > Morgen desktop app token > None.
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

    # Bearer token: env var override > desktop app discovery
    bearer_token = os.environ.get("MORGEN_BEARER_TOKEN")
    if not bearer_token:
        from guten_morgen.auth import get_bearer_token

        bearer_token = get_bearer_token(_default_cache_dir())

    return Settings(
        api_key=api_key,
        base_url=os.environ.get("MORGEN_BASE_URL", "https://api.morgen.so/v3"),
        timeout=float(os.environ.get("MORGEN_TIMEOUT", "30.0")),
        bearer_token=bearer_token or None,
    )
```

Add the cache dir helper (import `Path` at the top if not already):

```python
def _default_cache_dir() -> Path:
    """Return default cache directory for guten-morgen."""
    return Path.home() / ".cache" / "guten-morgen"
```

Note: The import of `get_bearer_token` is done lazily inside the function to avoid circular imports and to keep the auth module optional.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: all PASS

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/config.py`
Expected: Success

**Step 6: Commit**

```bash
git add src/guten_morgen/config.py tests/test_config.py
git commit -m "feat(config): wire bearer token into Settings"
```

---

### Task 4: Use Bearer Token in `MorgenClient`

**Files:**
- Modify: `src/guten_morgen/client.py`
- Modify: `tests/test_client.py`

**Step 1: Write the failing tests**

Add to `tests/test_client.py`:

```python
class TestBearerAuth:
    def test_uses_bearer_header_when_available(self) -> None:
        """Client uses Bearer auth when bearer_token is set."""
        requests_seen: list[httpx.Request] = []

        def capture_handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json={"data": {"tags": []}})

        transport = httpx.MockTransport(capture_handler)
        settings = Settings(api_key="api-key", bearer_token="my-bearer")
        client = MorgenClient(settings, transport=transport)
        client._request("GET", "/tags/list")
        assert requests_seen[0].headers["authorization"] == "Bearer my-bearer"

    def test_uses_apikey_when_no_bearer(self) -> None:
        """Client uses ApiKey auth when bearer_token is None."""
        requests_seen: list[httpx.Request] = []

        def capture_handler(request: httpx.Request) -> httpx.Response:
            requests_seen.append(request)
            return httpx.Response(200, json={"data": {"tags": []}})

        transport = httpx.MockTransport(capture_handler)
        settings = Settings(api_key="api-key", bearer_token=None)
        client = MorgenClient(settings, transport=transport)
        client._request("GET", "/tags/list")
        assert requests_seen[0].headers["authorization"] == "ApiKey api-key"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py::TestBearerAuth -v`
Expected: FAIL — bearer_token header not used (client still sends `ApiKey`)

**Step 3: Modify `client.py`**

Change the `__init__` method of `MorgenClient` to select auth header based on `settings.bearer_token`:

```python
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

    if settings.bearer_token:
        auth_header = f"Bearer {settings.bearer_token}"
    else:
        auth_header = f"ApiKey {settings.api_key}"

    kwargs: dict[str, Any] = {
        "base_url": settings.base_url,
        "headers": {"Authorization": auth_header},
        "timeout": settings.timeout,
    }
    if transport is not None:
        kwargs["transport"] = transport
    self._http = httpx.Client(**kwargs)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py -v`
Expected: all PASS (existing tests should also pass since they create `Settings(api_key=...)` without `bearer_token`, so it defaults to `None` and uses `ApiKey` as before)

**Step 5: Run mypy**

Run: `uv run mypy src/guten_morgen/client.py`
Expected: Success

**Step 6: Commit**

```bash
git add src/guten_morgen/client.py tests/test_client.py
git commit -m "feat(client): use bearer token auth when available"
```

---

### Task 5: Update `RateLimitError` Suggestion

**Files:**
- Modify: `src/guten_morgen/errors.py`
- Modify: `tests/test_cli_errors.py`

**Step 1: Write the failing test**

Add to `tests/test_cli_errors.py` (or create a new test if there isn't an appropriate test class):

```python
from guten_morgen.errors import RateLimitError


class TestRateLimitSuggestions:
    def test_includes_bearer_suggestion(self) -> None:
        err = RateLimitError("rate limited")
        suggestions_text = " ".join(err.suggestions)
        assert "Morgen desktop" in suggestions_text or "bearer" in suggestions_text
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_errors.py::TestRateLimitSuggestions -v`
Expected: FAIL — current suggestions don't mention bearer/desktop

**Step 3: Update `errors.py`**

Change the `RateLimitError` class:

```python
class RateLimitError(MorgenError):
    """API rate limit exceeded."""

    error_type = "rate_limit_error"
    suggestions = [
        "Wait for the Retry-After period before retrying",
        "Reduce request frequency",
        "Install Morgen desktop app for 5x higher rate limits (bearer token auth)",
    ]
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_errors.py::TestRateLimitSuggestions -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/guten_morgen/errors.py tests/test_cli_errors.py
git commit -m "fix(errors): add bearer token suggestion to rate limit error"
```

---

### Task 6: Full Test Suite + Mypy

**Files:** None (verification only)

**Step 1: Run full test suite**

Run: `uv run pytest -x -q --cov`
Expected: all tests pass, coverage >= 90%

**Step 2: Run mypy strict**

Run: `uv run mypy src/`
Expected: Success (no errors)

**Step 3: Run pre-commit hooks**

Run: `uv run pre-commit run --all-files`
Expected: all pass

**Step 4: Commit any fixups**

If any linting/formatting changes were made:

```bash
git add -A
git commit -m "chore: lint and format fixes"
```

---

### Task 7: Manual Smoke Test

**Files:** None (verification only)

**Step 1: Verify bearer token is picked up**

Run: `gm tags list --json 2>/dev/null | head -1`

Then check what auth was used by looking at the rate limit header:

Run: `curl -s -D- "https://api.morgen.so/v3/tags/list" -H "Authorization: ApiKey $(grep api_key ~/.config/guten-morgen/config.toml | sed 's/.*= *"//;s/".*//')" 2>/dev/null | grep ratelimit-remaining`

If `gm` used bearer auth, the API key's `ratelimit-remaining` should be unchanged (not decremented) after the `gm` call.

**Step 2: Verify fallback**

Temporarily rename the Morgen desktop config to simulate it being missing:

```bash
mv ~/Library/Application\ Support/Morgen/config.json ~/Library/Application\ Support/Morgen/config.json.bak
gm tags list --json 2>/dev/null | head -1  # should still work via API key
mv ~/Library/Application\ Support/Morgen/config.json.bak ~/Library/Application\ Support/Morgen/config.json
```

**Step 3: Check cache was written**

Run: `cat ~/.cache/guten-morgen/_bearer.json | python3 -m json.tool`
Expected: JSON with `token` and `expires_at` fields
