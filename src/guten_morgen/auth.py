"""Bearer token auth via Morgen desktop app."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx


def find_morgen_desktop_config() -> Path | None:
    """Locate the Morgen desktop app config.json.

    Search order:
    1. macOS: ~/Library/Application Support/Morgen/config.json
    2. Linux/XDG: $XDG_CONFIG_HOME/Morgen/config.json (or ~/.config/Morgen/)
    """
    home = Path(os.environ.get("HOME", str(Path.home())))

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
    except Exception:  # noqa: BLE001
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
    """Save bearer token to cache with restricted permissions."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / _BEARER_CACHE_FILE
    cache_file.write_text(json.dumps({"token": token, "expires_at": expires_at}))
    cache_file.chmod(0o600)


def get_bearer_token(cache_dir: Path) -> str | None:
    """Get a valid bearer token, using cache or refreshing as needed.

    Returns an access token string, or None if bearer auth is unavailable.
    All failures are silent -- caller falls back to API key auth.
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
