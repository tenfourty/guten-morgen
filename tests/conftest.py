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
    {
        "id": "acc-1",
        "name": "Work Google",
        "providerUserDisplayName": "Test User",
        "preferredEmail": "test@example.com",
        "integrationId": "google",
        "integrationGroups": ["calendars"],
    },
    {
        "id": "acc-2",
        "name": "Personal",
        "providerUserDisplayName": "Test Personal",
        "preferredEmail": "personal@example.com",
        "integrationId": "caldav",
        "integrationGroups": ["calendars"],
    },
]

FAKE_CALENDARS = [
    {
        "id": "cal-1",
        "calendarId": "cal-1",
        "accountId": "acc-1",
        "name": "Work",
        "color": "#4285f4",
        "myRights": "rw",
        "writable": True,
    },
    {
        "id": "cal-2",
        "calendarId": "cal-2",
        "accountId": "acc-1",
        "name": "Holidays",
        "color": "#0b8043",
        "myRights": "r",
        "writable": False,
    },
]

FAKE_EVENTS = [
    {
        "id": "evt-1",
        "title": "Standup",
        "start": "2026-02-17T09:00:00",
        "duration": "PT30M",
        "calendarId": "cal-1",
        "accountId": "acc-1",
        "attendees": [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ],
        "location": "https://meet.google.com/abc-defg-hij",
    },
    {
        "id": "evt-2",
        "title": "Lunch",
        "start": "2026-02-17T12:00:00",
        "duration": "PT1H",
        "calendarId": "cal-1",
        "accountId": "acc-1",
        "location": "Café de Flore",
    },
]

FAKE_TASKS = [
    {
        "id": "task-1",
        "title": "Review PR",
        "progress": "needs-action",
        "priority": 2,
        "due": "2026-02-17T23:59:59Z",
        "taskListId": "inbox",
    },
    {
        "id": "task-2",
        "title": "Write docs",
        "progress": "needs-action",
        "priority": 1,
        "taskListId": "inbox",
    },
    {
        "id": "task-3",
        "title": "Old overdue task",
        "progress": "needs-action",
        "priority": 3,
        "due": "2025-10-15T23:59:59Z",
        "taskListId": "inbox",
    },
    {
        "id": "task-4",
        "title": "Completed task",
        "progress": "completed",
        "priority": 0,
        "due": "2026-02-16T23:59:59Z",
        "taskListId": "inbox",
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
    "/v3/integrations/accounts/list": {"data": {"accounts": FAKE_ACCOUNTS}},
    "/v3/calendars/list": {"data": {"calendars": FAKE_CALENDARS}},
    "/v3/events/list": {"data": {"events": FAKE_EVENTS}},
    "/v3/tasks/list": {"data": {"tasks": FAKE_TASKS}},
    "/v3/tags/list": FAKE_TAGS,  # Tags API returns flat list
}


def _item_key_from_path(path: str) -> str:
    """Derive the singular item key from an API path (e.g. /v3/tasks/create -> task)."""
    # Strip /v3/ prefix and get the resource name
    parts = path.replace("/v3/", "").split("/")
    resource = parts[0] if parts else "item"
    # Singular: tasks -> task, events -> event, tags -> tag
    if resource.endswith("s"):
        return resource[:-1]
    return resource


def mock_transport_handler(request: httpx.Request) -> httpx.Response:
    """Route mock API requests to fake data."""
    path = request.url.path
    if path in ROUTES:
        return httpx.Response(200, json=ROUTES[path])

    # POST endpoints for create/update/delete — echo back wrapped in envelope
    if request.method == "POST":
        try:
            body = json.loads(request.content)
        except (json.JSONDecodeError, ValueError):
            body = {}
        body.setdefault("id", "new-id")
        # Determine the wrapper key from the path
        item_key = _item_key_from_path(path)
        if "/delete" in path:
            return httpx.Response(200, json=body)
        return httpx.Response(200, json={"data": {item_key: body}})

    # GET with ?id= parameter — wrap in envelope
    if "id=" in str(request.url):
        item_key = _item_key_from_path(path)
        item = {"id": "found-id", "title": "Found item"}
        return httpx.Response(200, json={"data": {item_key: item}})

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
