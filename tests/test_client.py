"""Tests for MorgenClient."""

from __future__ import annotations

import json

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
