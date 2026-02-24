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

_PROJECT_CONFIG = "guten-morgen.toml"
_APP_DIR = "guten-morgen"
_XDG_CONFIG = "config.toml"


def find_config() -> Path | None:
    """Discover config file.

    Search order (first existing file wins):
    1. $GM_CONFIG env var (explicit override)
    2. guten-morgen.toml — walk up from CWD (project-local config)
    3. $XDG_CONFIG_HOME/guten-morgen/config.toml (default ~/.config/)
    """
    # 1. Explicit env var
    env_path = os.environ.get("GM_CONFIG")
    if env_path:
        p = Path(env_path)
        if not p.is_file():
            raise ConfigError(
                f"GM_CONFIG points to missing file: {env_path}",
                suggestions=["Check the path or unset GM_CONFIG to use auto-discovery"],
            )
        return p

    # 2. Walk up from CWD looking for guten-morgen.toml
    cwd = Path.cwd()
    for d in [cwd, *cwd.parents]:
        candidate = d / _PROJECT_CONFIG
        if candidate.is_file():
            return candidate

    # 3. XDG
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_home:
        xdg_path = Path(xdg_home) / _APP_DIR / _XDG_CONFIG
    else:
        xdg_path = Path.home() / ".config" / _APP_DIR / _XDG_CONFIG
    if xdg_path.is_file():
        return xdg_path

    return None


def load_config_toml(path: Path | None = None) -> dict[str, object]:
    """Load and return raw TOML config dict. Empty dict if no file."""
    if path is None:
        path = find_config()
    if path is None:
        return {}
    with open(path, "rb") as f:
        result: dict[str, object] = tomllib.load(f)
        return result


@dataclass
class Settings:
    """Morgen API configuration."""

    api_key: str
    base_url: str = "https://api.morgen.so/v3"
    timeout: float = 30.0
    max_retries: int = 2
    bearer_token: str | None = None


def _default_cache_dir() -> Path:
    """Return default cache directory for guten-morgen."""
    return Path.home() / ".cache" / "guten-morgen"


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
