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
