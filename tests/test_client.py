"""Tests for MorgenClient."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from morgen.client import MorgenClient
from morgen.config import Settings
from morgen.errors import AuthenticationError, MorgenAPIError, NotFoundError, RateLimitError


def _mock_transport(status: int, body: dict | str = "", headers: dict[str, str] | None = None) -> httpx.MockTransport:
    """Create a MockTransport that returns a fixed response."""

    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps(body).encode() if isinstance(body, dict) else body.encode() if body else b""
        return httpx.Response(
            status_code=status,
            content=content,
            headers=headers or {},
        )

    return httpx.MockTransport(handler)


def _make_client(transport: httpx.MockTransport) -> MorgenClient:
    settings = Settings(api_key="test-key")
    return MorgenClient(settings, transport=transport)


class TestRequestErrorMapping:
    def test_401_raises_auth_error(self) -> None:
        client = _make_client(_mock_transport(401, "Unauthorized"))
        with pytest.raises(AuthenticationError, match="Invalid or missing API key"):
            client._request("GET", "/test")

    def test_429_raises_rate_limit(self) -> None:
        client = _make_client(_mock_transport(429, "Rate limited", {"Retry-After": "30"}))
        with pytest.raises(RateLimitError, match="Retry after 30s"):
            client._request("GET", "/test")

    def test_404_raises_not_found(self) -> None:
        client = _make_client(_mock_transport(404, "Not found"))
        with pytest.raises(NotFoundError, match="/test"):
            client._request("GET", "/test")

    def test_400_raises_api_error(self) -> None:
        client = _make_client(_mock_transport(400, "Bad request"))
        with pytest.raises(MorgenAPIError, match="400"):
            client._request("GET", "/test")

    def test_200_returns_json(self) -> None:
        client = _make_client(_mock_transport(200, {"data": "ok"}))
        result = client._request("GET", "/test")
        assert result == {"data": "ok"}

    def test_204_returns_none(self) -> None:
        client = _make_client(_mock_transport(204))
        result = client._request("GET", "/test")
        assert result is None


class TestListAllEvents:
    """Tests for list_all_events — multi-account fan-out + dedup."""

    def test_queries_both_accounts(self, client: MorgenClient) -> None:
        """Events from all calendar-capable accounts are returned."""
        events = client.list_all_events("2026-02-17T00:00:00", "2026-02-17T23:59:59")
        titles = [e["title"] for e in events]
        assert "Standup" in titles
        assert "Dentist" in titles

    def test_deduplicates_via_morgen(self, client: MorgenClient) -> None:
        """Synced copies with '(via Morgen)' in title are removed."""
        events = client.list_all_events("2026-02-17T00:00:00", "2026-02-17T23:59:59")
        titles = [e["title"] for e in events]
        assert "Standup (via Morgen)" not in titles

    def test_keeps_all_originals(self, client: MorgenClient) -> None:
        """Original events from both accounts are preserved."""
        events = client.list_all_events("2026-02-17T00:00:00", "2026-02-17T23:59:59")
        # acc-1: Standup, Lunch, Tasks and Deep Work
        # acc-2: Dentist (synced copy removed)
        assert len(events) == 4


class TestListAllEventsFiltering:
    """Tests for list_all_events filtering: account_keys, calendar_names, active_only."""

    def test_filter_by_account_key(self, client: MorgenClient) -> None:
        """Only events from matching accounts are returned."""
        events = client.list_all_events(
            "2026-02-17T00:00:00",
            "2026-02-17T23:59:59",
            account_keys=["test@example.com:google"],
        )
        account_ids = {e["accountId"] for e in events}
        assert account_ids == {"acc-1"}

    def test_filter_by_email_only(self, client: MorgenClient) -> None:
        """Email-only key matches any provider for that email."""
        events = client.list_all_events(
            "2026-02-17T00:00:00",
            "2026-02-17T23:59:59",
            account_keys=["personal@example.com"],
        )
        account_ids = {e["accountId"] for e in events}
        assert account_ids == {"acc-2"}

    def test_active_only_filters_inactive_calendars(self, client: MorgenClient) -> None:
        """active_only=True skips calendars with isActiveByDefault=False."""
        # cal-2 (Holidays) has isActiveByDefault=False, belongs to acc-1
        # Events from cal-2 should be excluded — but our fake events are all on cal-1/cal-3
        # So count should stay the same since no events are on cal-2
        events = client.list_all_events(
            "2026-02-17T00:00:00",
            "2026-02-17T23:59:59",
            active_only=True,
        )
        assert len(events) == 4  # cal-2 has no events, so no change

    def test_filter_by_calendar_name(self, client: MorgenClient) -> None:
        """Only events from calendars with matching names are returned."""
        events = client.list_all_events(
            "2026-02-17T00:00:00",
            "2026-02-17T23:59:59",
            calendar_names=["Personal Calendar"],
        )
        # Only acc-2's "Personal Calendar" matches, after dedup only "Dentist" remains
        titles = [e["title"] for e in events]
        assert "Dentist" in titles
        assert "Standup" not in titles

    def test_combined_account_and_calendar_filter(self, client: MorgenClient) -> None:
        """Account + calendar name filters combine."""
        events = client.list_all_events(
            "2026-02-17T00:00:00",
            "2026-02-17T23:59:59",
            account_keys=["test@example.com:google"],
            calendar_names=["Work"],
        )
        # acc-1 matches, only "Work" calendar (cal-1) events
        titles = [e["title"] for e in events]
        assert "Standup" in titles
        assert "Lunch" in titles

    def test_calendar_names_bypass_active_only(self, client: MorgenClient) -> None:
        """Explicit calendar_names includes inactive calendars despite active_only=True."""
        # cal-2 "Holidays" has isActiveByDefault=False — verify it's still queried
        from unittest.mock import patch

        call_args: list[tuple[str, list[str]]] = []
        original = client.list_events

        def spy(account_id: str, calendar_ids: list[str], *a: object, **kw: object) -> list[dict[str, Any]]:
            call_args.append((account_id, calendar_ids))
            return original(account_id, calendar_ids, *a, **kw)  # type: ignore[arg-type]

        with patch.object(client, "list_events", side_effect=spy):
            client.list_all_events(
                "2026-02-17T00:00:00",
                "2026-02-17T23:59:59",
                calendar_names=["Holidays"],
                active_only=True,
            )
        # cal-2 ("Holidays", inactive) should have been included in the query
        acc1_calls = [cids for aid, cids in call_args if aid == "acc-1"]
        assert acc1_calls, "acc-1 should have been queried"
        assert "cal-2" in acc1_calls[0]

    def test_no_matching_accounts_returns_empty(self, client: MorgenClient) -> None:
        """Non-matching account key returns no events."""
        events = client.list_all_events(
            "2026-02-17T00:00:00",
            "2026-02-17T23:59:59",
            account_keys=["nobody@nowhere.com:google"],
        )
        assert events == []
