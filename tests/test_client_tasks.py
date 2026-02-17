"""Tests for multi-source task client methods."""

from __future__ import annotations

from morgen.client import MorgenClient


class TestListTaskAccounts:
    def test_returns_only_task_accounts(self, client: MorgenClient) -> None:
        accounts = client.list_task_accounts()
        integration_ids = [a["integrationId"] for a in accounts]
        assert "linear" in integration_ids
        assert "notion" in integration_ids
        # Calendar-only accounts should NOT appear
        assert "google" not in integration_ids
        assert "caldav" not in integration_ids

    def test_cached(self, client: MorgenClient) -> None:
        first = client.list_task_accounts()
        second = client.list_task_accounts()
        assert first == second


class TestListAllTasks:
    def test_returns_all_sources(self, client: MorgenClient) -> None:
        result = client.list_all_tasks()
        sources = {t.get("integrationId", "morgen") for t in result["tasks"]}
        assert "morgen" in sources
        assert "linear" in sources
        assert "notion" in sources

    def test_includes_label_defs(self, client: MorgenClient) -> None:
        result = client.list_all_tasks()
        assert "labelDefs" in result
        assert len(result["labelDefs"]) > 0

    def test_source_filter(self, client: MorgenClient) -> None:
        result = client.list_all_tasks(source="linear")
        sources = {t.get("integrationId") for t in result["tasks"]}
        assert sources == {"linear"}

    def test_morgen_only(self, client: MorgenClient) -> None:
        result = client.list_all_tasks(source="morgen")
        sources = {t.get("integrationId", "morgen") for t in result["tasks"]}
        assert sources == {"morgen"}
