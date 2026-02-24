"""Bearer token auth via Morgen desktop app."""

from __future__ import annotations

import json
import os
from pathlib import Path


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
