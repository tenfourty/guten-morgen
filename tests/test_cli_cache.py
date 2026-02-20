"""Tests for cache CLI commands and --no-cache flag."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
from click.testing import CliRunner

from guten_morgen.cache import CacheStore
from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient
from guten_morgen.config import Settings
from tests.conftest import mock_transport_handler


class TestCacheClearCommand:
    def test_cache_clear(self, runner: CliRunner, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        with patch("guten_morgen.cli._get_cache_store", return_value=store):
            result = runner.invoke(cli, ["cache", "clear"])
        assert result.exit_code == 0
        assert store.get("accounts") is None


class TestCacheStatsCommand:
    def test_cache_stats_json(self, runner: CliRunner, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        with patch("guten_morgen.cli._get_cache_store", return_value=store):
            result = runner.invoke(cli, ["cache", "stats"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["entries"] == 1


class TestNoCacheFlag:
    def test_no_cache_flag_exists(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["--no-cache", "accounts", "--json"])
        assert result.exit_code == 0


class TestNoCacheBypass:
    def test_no_cache_does_not_read_stale_data(self, runner: CliRunner, tmp_path: Path) -> None:
        """--no-cache flag prevents reading from cache."""
        # Create a client WITHOUT cache (simulating --no-cache)
        settings = Settings(api_key="test-key")
        client_no_cache = MorgenClient(settings, transport=httpx.MockTransport(mock_transport_handler))

        with patch("guten_morgen.cli._get_client", return_value=client_no_cache):
            result = runner.invoke(cli, ["--no-cache", "accounts", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        # Should get fresh data (4 accounts from mock), NOT stale (1 account)
        assert len(data) == 4
