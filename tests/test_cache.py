"""Tests for CacheStore."""

from __future__ import annotations

import time
from pathlib import Path

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
