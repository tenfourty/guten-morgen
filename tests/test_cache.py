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
        store.invalidate("tasks")
        assert store.get("accounts") == [{"id": "a1"}]


class TestCacheClear:
    def test_clear_removes_all(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        store.set("tasks/list", [{"id": "t1"}], ttl=3600)
        store.clear()
        assert store.get("accounts") is None
        assert store.get("tasks/list") is None


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


class TestCacheResilience:
    def test_corrupt_data_file_returns_none(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        store._data_path("accounts").write_text("not json{{{")
        assert store.get("accounts") is None

    def test_corrupt_meta_file_starts_fresh(self, tmp_path: Path) -> None:
        (tmp_path / "_meta.json").write_text("not json{{{")
        store = CacheStore(cache_dir=tmp_path)
        assert store.get("anything") is None

    def test_missing_data_file_returns_none(self, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        store._data_path("accounts").unlink()
        assert store.get("accounts") is None
