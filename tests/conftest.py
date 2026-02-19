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
        "isActiveByDefault": True,
    },
    {
        "id": "cal-2",
        "calendarId": "cal-2",
        "accountId": "acc-1",
        "name": "Holidays",
        "color": "#0b8043",
        "myRights": "r",
        "writable": False,
        "isActiveByDefault": False,
    },
    {
        "id": "cal-3",
        "calendarId": "cal-3",
        "accountId": "acc-2",
        "name": "Personal Calendar",
        "color": "#e67c73",
        "myRights": "rw",
        "writable": True,
        "isActiveByDefault": True,
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
        "participants": {
            "p1": {"name": "Alice", "email": "alice@example.com", "kind": "individual"},
            "p2": {"name": "Bob", "email": "bob@example.com", "kind": "individual"},
            "p3": {"name": "Room 42", "email": "room42@example.com", "kind": "resource"},
        },
        "locations": {
            "loc1": {"name": "https://meet.google.com/abc-defg-hij"},
        },
    },
    {
        "id": "evt-2",
        "title": "Lunch",
        "start": "2026-02-17T12:00:00",
        "duration": "PT1H",
        "calendarId": "cal-1",
        "accountId": "acc-1",
    },
    {
        "id": "evt-3",
        "title": "Tasks and Deep Work",
        "start": "2026-02-17T14:00:00",
        "duration": "PT2H",
        "calendarId": "cal-1",
        "accountId": "acc-1",
        "morgen.so:metadata": {
            "frameFilterMql": '{"$or":[]}',
            "isAutoScheduled": False,
            "isFlexible": False,
            "canBeCompleted": False,
        },
    },
]

FAKE_EVENTS_ACC2 = [
    {
        "id": "evt-synced-1",
        "title": "Standup (via Morgen)",
        "start": "2026-02-17T09:00:00",
        "duration": "PT30M",
        "calendarId": "cal-3",
        "accountId": "acc-2",
    },
    {
        "id": "evt-personal-1",
        "title": "Dentist",
        "start": "2026-02-17T16:00:00",
        "duration": "PT1H",
        "calendarId": "cal-3",
        "accountId": "acc-2",
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

# Task-integration accounts (Linear, Notion)
FAKE_TASK_ACCOUNTS = [
    {
        "id": "acc-linear",
        "providerUserDisplayName": "test@company.com",
        "preferredEmail": "test@company.com",
        "integrationId": "linear",
        "integrationGroups": ["tasks"],
    },
    {
        "id": "acc-notion",
        "providerUserDisplayName": "Test User",
        "preferredEmail": "test@example.com",
        "integrationId": "notion",
        "integrationGroups": ["tasks"],
    },
]

FAKE_LINEAR_TASKS = {
    "data": {
        "tasks": [
            {
                "@type": "Task",
                "id": "linear-task-1",
                "title": "Budget planning",
                "progress": "needs-action",
                "priority": 0,
                "due": "2026-02-20",
                "integrationId": "linear",
                "accountId": "acc-linear",
                "links": {
                    "original": {
                        "@type": "Link",
                        "href": "https://linear.app/company/issue/ENG-1740/budget-planning",
                        "title": "Open in Linear",
                    }
                },
                "labels": [
                    {"id": "identifier", "value": "ENG-1740"},
                    {"id": "state", "value": "state-uuid-1"},
                ],
            },
        ],
        "labelDefs": [
            {
                "id": "state",
                "label": "Status",
                "type": "enum",
                "values": [
                    {"value": "state-uuid-1", "label": "In Progress"},
                ],
            },
        ],
        "spaces": [],
    }
}

FAKE_NOTION_TASKS = {
    "data": {
        "tasks": [
            {
                "@type": "Task",
                "id": "notion-task-1",
                "title": "Update Career Ladder",
                "progress": "needs-action",
                "priority": 5,
                "due": "2026-03-01",
                "integrationId": "notion",
                "accountId": "acc-notion",
                "links": {
                    "original": {
                        "@type": "Link",
                        "href": "https://www.notion.so/14ca119c1d9f80ce943a",
                        "title": "Open in Notion",
                    }
                },
                "labels": [
                    {"id": "notion%3A%2F%2Fprojects%2Fstatus_property", "value": "planned"},
                    {"id": "notion%3A%2F%2Fprojects%2Fpriority_property", "value": "priority_high"},
                ],
            },
        ],
        "labelDefs": [
            {
                "id": "notion%3A%2F%2Fprojects%2Fstatus_property",
                "label": "Status",
                "type": "enum",
                "values": [
                    {"value": "planned", "label": "Planning"},
                    {"value": "in-progress", "label": "In Progress"},
                ],
            },
            {
                "id": "notion%3A%2F%2Fprojects%2Fpriority_property",
                "label": "Priority",
                "type": "enum",
                "values": [
                    {"value": "priority_high", "label": "High"},
                    {"value": "priority_medium", "label": "Medium"},
                ],
            },
        ],
        "spaces": [{"id": "space-1", "name": "Projects"}],
    }
}

# Extend FAKE_ACCOUNTS so list_accounts() returns task-integration accounts too
FAKE_ACCOUNTS.extend(FAKE_TASK_ACCOUNTS)


# ---------------------------------------------------------------------------
# Mock transport
# ---------------------------------------------------------------------------

ROUTES: dict[str, Any] = {
    "/v3/integrations/accounts/list": {"data": {"accounts": FAKE_ACCOUNTS}},
    "/v3/calendars/list": {"data": {"calendars": FAKE_CALENDARS}},
    "/v3/tasks/list": {"data": {"tasks": FAKE_TASKS}},
    "/v3/tags/list": FAKE_TAGS,  # Tags API returns flat list
}

# Events routing by accountId
_EVENTS_BY_ACCOUNT: dict[str, list[dict[str, Any]]] = {
    "acc-1": FAKE_EVENTS,
    "acc-2": FAKE_EVENTS_ACC2,
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

    # Route events by accountId query param
    if path == "/v3/events/list":
        account_id = dict(request.url.params).get("accountId", "acc-1")
        events = _EVENTS_BY_ACCOUNT.get(account_id, [])
        return httpx.Response(200, json={"data": {"events": events}})

    # Route tasks by accountId query param (external integrations)
    if path == "/v3/tasks/list":
        account_id = dict(request.url.params).get("accountId")
        if account_id == "acc-linear":
            return httpx.Response(200, json=FAKE_LINEAR_TASKS)
        if account_id == "acc-notion":
            return httpx.Response(200, json=FAKE_NOTION_TASKS)
        # Fall through to ROUTES for default (morgen-native tasks)

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
    """Patch _get_client and config to return mock-backed client with no-op filter."""
    from morgen.groups import MorgenConfig

    with (
        patch("morgen.cli._get_client", return_value=client),
        patch("morgen.cli.load_morgen_config", return_value=MorgenConfig()),
    ):
        yield client
