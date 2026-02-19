"""Tests for MorgenClient cache integration."""

from __future__ import annotations

from pathlib import Path

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
        assert len(result) == 4
        assert cache.get("accounts") is not None

    def test_second_call_returns_cached(self, tmp_path: Path) -> None:
        client, cache = _make_client(tmp_path)
        client.list_accounts()  # populate the cache
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
    def test_client_without_cache(self) -> None:
        settings = Settings(api_key="test-key")
        transport = httpx.MockTransport(mock_transport_handler)
        client = MorgenClient(settings, transport=transport)
        result = client.list_accounts()
        assert len(result) == 4
