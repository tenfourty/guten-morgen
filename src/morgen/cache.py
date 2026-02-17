"""File-based TTL cache for Morgen API responses."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

# TTL constants (seconds)
TTL_ACCOUNTS = 86400  # 24 hours
TTL_CALENDARS = 86400  # 24 hours
TTL_TAGS = 14400  # 4 hours
TTL_EVENTS = 1800  # 30 minutes
TTL_TASKS = 1800  # 30 minutes
TTL_SINGLE = 300  # 5 minutes (get by ID)

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
            raw: dict[str, dict[str, float]] = json.loads(self._meta_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return raw

    def _save_meta(self) -> None:
        self._meta_path.write_text(json.dumps(self._meta))

    def _data_path(self, key: str) -> Path:
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
