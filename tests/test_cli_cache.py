"""Tests for cache CLI commands and --no-cache flag."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from morgen.cache import CacheStore
from morgen.cli import cli
from morgen.client import MorgenClient


class TestCacheClearCommand:
    def test_cache_clear(self, runner: CliRunner, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        with patch("morgen.cli._get_cache_store", return_value=store):
            result = runner.invoke(cli, ["cache", "clear"])
        assert result.exit_code == 0
        assert store.get("accounts") is None


class TestCacheStatsCommand:
    def test_cache_stats_json(self, runner: CliRunner, tmp_path: Path) -> None:
        store = CacheStore(cache_dir=tmp_path)
        store.set("accounts", [{"id": "a1"}], ttl=3600)
        with patch("morgen.cli._get_cache_store", return_value=store):
            result = runner.invoke(cli, ["cache", "stats"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["entries"] == 1


class TestNoCacheFlag:
    def test_no_cache_flag_exists(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["--no-cache", "accounts", "--json"])
        assert result.exit_code == 0
