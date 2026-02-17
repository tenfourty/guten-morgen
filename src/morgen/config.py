"""Settings loaded from .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from morgen.errors import ConfigError

# Walk up from this file to find project root .env
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _find_env_file() -> Path | None:
    """Find .env file starting from project root."""
    env_path = _PROJECT_ROOT / ".env"
    if env_path.exists():
        return env_path
    return None


@dataclass
class Settings:
    """Morgen API configuration."""

    api_key: str
    base_url: str = "https://api.morgen.so/v3"
    timeout: float = 30.0


def load_settings() -> Settings:
    """Load settings from environment / .env file."""
    env_file = _find_env_file()
    if env_file:
        load_dotenv(env_file)

    api_key = os.environ.get("MORGEN_API_KEY", "")
    if not api_key:
        raise ConfigError(
            "MORGEN_API_KEY is not set",
            suggestions=["Copy .env.example to .env and fill in MORGEN_API_KEY"],
        )

    return Settings(
        api_key=api_key,
        base_url=os.environ.get("MORGEN_BASE_URL", "https://api.morgen.so/v3"),
        timeout=float(os.environ.get("MORGEN_TIMEOUT", "30.0")),
    )
