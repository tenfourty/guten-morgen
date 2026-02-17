"""Shared test fixtures."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from click.testing import CliRunner

from morgen.client import MorgenClient
from morgen.config import Settings

# ---------------------------------------------------------------------------
# Fake API data
# ---------------------------------------------------------------------------

FAKE_ACCOUNTS = [
    {"accountId": "acc-1", "name": "Work Google", "email": "jeremy@example.com", "providerId": "google"},
    {"accountId": "acc-2", "name": "Personal", "email": "j@personal.com", "providerId": "caldav"},
]

FAKE_CALENDARS = [
    {"calendarId": "cal-1", "accountId": "acc-1", "name": "Work", "color": "#4285f4", "writable": True},
    {"calendarId": "cal-2", "accountId": "acc-1", "name": "Holidays", "color": "#0b8043", "writable": False},
]

FAKE_EVENTS = [
    {
        "id": "evt-1",
        "title": "Standup",
        "start": "2026-02-17T09:00:00Z",
        "end": "2026-02-17T09:30:00Z",
        "calendarId": "cal-1",
        "accountId": "acc-1",
    },
    {
        "id": "evt-2",
        "title": "Lunch",
        "start": "2026-02-17T12:00:00Z",
        "end": "2026-02-17T13:00:00Z",
        "calendarId": "cal-1",
        "accountId": "acc-1",
    },
]

FAKE_TASKS = [
    {
        "id": "task-1",
        "title": "Review PR",
        "status": "open",
        "priority": 2,
        "due": "2026-02-17T23:59:59Z",
    },
    {
        "id": "task-2",
        "title": "Write docs",
        "status": "open",
        "priority": 1,
    },
]

FAKE_TAGS = [
    {"id": "tag-1", "name": "urgent", "color": "#ff0000"},
    {"id": "tag-2", "name": "personal", "color": "#00ff00"},
]


# ---------------------------------------------------------------------------
# Mock transport
# ---------------------------------------------------------------------------

ROUTES: dict[str, Any] = {
    "/v3/integrations/accounts/list": {"data": FAKE_ACCOUNTS},
    "/v3/calendars/list": {"data": FAKE_CALENDARS},
    "/v3/events/list": {"data": FAKE_EVENTS},
    "/v3/tasks/list": {"data": FAKE_TASKS},
    "/v3/tags/list": {"data": FAKE_TAGS},
}


def mock_transport_handler(request: httpx.Request) -> httpx.Response:
    """Route mock API requests to fake data."""
    path = request.url.path
    if path in ROUTES:
        return httpx.Response(200, json=ROUTES[path])

    # POST endpoints for create/update/delete — echo back with an id
    if request.method == "POST":
        try:
            body = json.loads(request.content)
        except (json.JSONDecodeError, ValueError):
            body = {}
        body.setdefault("id", "new-id")
        return httpx.Response(200, json=body)

    # GET with ?id= parameter
    if "id=" in str(request.url):
        return httpx.Response(200, json={"id": "found-id", "title": "Found item"})

    return httpx.Response(404, json={"error": "not found"})


@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    """MockTransport for API tests."""
    return httpx.MockTransport(mock_transport_handler)


@pytest.fixture
def client(mock_transport: httpx.MockTransport) -> MorgenClient:
    """MorgenClient backed by mock transport."""
    settings = Settings(api_key="test-key")
    return MorgenClient(settings, transport=mock_transport)


@pytest.fixture
def runner() -> CliRunner:
    """Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_client(client: MorgenClient):  # type: ignore[no-untyped-def]
    """Patch _get_client to return mock-backed client."""
    with patch("morgen.cli._get_client", return_value=client):
        yield client
