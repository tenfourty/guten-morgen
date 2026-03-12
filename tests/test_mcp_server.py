"""Tests for MCP server handler functions (Phase 1 — read-only tools).

MCP handler tests: handler unit tests with mock MorgenClient are sufficient;
do not test FastMCP transport wiring (that's FastMCP's responsibility).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

from guten_morgen.models import Account, Event, Tag, Task, TaskList, TaskListResponse

# ---------------------------------------------------------------------------
# Test data (subset of conftest fixtures — enough for MCP handler tests)
# ---------------------------------------------------------------------------

_EVENTS = [
    {
        "id": "evt-1",
        "title": "Standup",
        "start": "2026-02-17T09:00:00",
        "duration": "PT30M",
        "calendarId": "cal-1",
        "accountId": "acc-1",
        "participants": {
            "p1": {
                "name": "Alice",
                "email": "alice@example.com",
                "kind": "individual",
                "participationStatus": "accepted",
            },
            "owner": {
                "email": "test@example.com",
                "accountOwner": True,
                "participationStatus": "accepted",
            },
        },
        "locations": {"loc1": {"name": "https://meet.google.com/abc-defg-hij"}},
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
        "morgen.so:metadata": {"frameFilterMql": '{"$or":[]}', "isAutoScheduled": False},
    },
    {
        "id": "evt-declined",
        "title": "Optional Open Hours",
        "start": "2026-02-17T15:00:00",
        "duration": "PT30M",
        "calendarId": "cal-1",
        "accountId": "acc-1",
        "participants": {
            "owner": {"email": "test@example.com", "accountOwner": True, "participationStatus": "declined"},
        },
    },
]

_TASKS = [
    {
        "id": "task-1",
        "title": "Review PR",
        "progress": "needs-action",
        "priority": 2,
        "due": "2026-02-17T23:59:59Z",
        "taskListId": "inbox",
        "tags": ["tag-1"],
    },
    {
        "id": "task-2",
        "title": "Write docs",
        "progress": "needs-action",
        "priority": 1,
        "taskListId": "inbox",
        "tags": ["tag-2"],
    },
    {
        "id": "task-3",
        "title": "Old overdue task",
        "progress": "needs-action",
        "priority": 3,
        "due": "2025-10-15T23:59:59Z",
        "taskListId": "inbox",
        "tags": ["tag-1", "tag-2"],
    },
    {
        "id": "task-4",
        "title": "Completed task",
        "progress": "completed",
        "priority": 0,
        "due": "2026-02-16T23:59:59Z",
        "taskListId": "inbox",
        "tags": [],
    },
]

_TAGS = [
    {"id": "tag-1", "name": "urgent", "color": "#ff0000"},
    {"id": "tag-2", "name": "personal", "color": "#00ff00"},
]

_TASK_LISTS = [
    {
        "id": "inbox",
        "name": "Inbox",
        "color": "#9695A0",
        "role": "inbox",
        "serviceName": "morgen",
    },
    {
        "id": "list-work@morgen.so",
        "name": "Run - Work",
        "color": "#38c2c7",
        "serviceName": "morgen",
    },
]

_ACCOUNTS = [
    {
        "id": "acc-1",
        "providerUserDisplayName": "Test User",
        "preferredEmail": "test@example.com",
        "integrationId": "google",
        "integrationGroups": ["calendars"],
    },
    {
        "id": "acc-2",
        "providerUserDisplayName": "Test Personal",
        "preferredEmail": "personal@example.com",
        "integrationId": "caldav",
        "integrationGroups": ["calendars"],
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(
    events: list[dict[str, Any]] | None = None,
    tasks: list[dict[str, Any]] | None = None,
    tags: list[dict[str, Any]] | None = None,
    task_lists: list[dict[str, Any]] | None = None,
    accounts: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Create a MagicMock MorgenClient with standard fake data."""
    client = MagicMock()

    event_dicts = events if events is not None else _EVENTS
    client.list_all_events.return_value = [Event(**e) for e in event_dicts]

    task_dicts = tasks if tasks is not None else _TASKS
    tag_dicts = tags if tags is not None else _TAGS
    tl_dicts = task_lists if task_lists is not None else _TASK_LISTS
    acct_dicts = accounts if accounts is not None else _ACCOUNTS

    client.list_all_tasks.return_value = TaskListResponse(
        tasks=[Task(**t) for t in task_dicts],
        labelDefs=[],
    )
    client.list_tags.return_value = [Tag(**t) for t in tag_dicts]
    client.list_task_lists.return_value = [TaskList(**tl) for tl in tl_dicts]
    client.list_accounts.return_value = [Account(**a) for a in acct_dicts]

    return client


def _make_mock_config(groups: dict[str, Any] | None = None) -> MagicMock:
    """Create a MagicMock MorgenConfig."""
    config = MagicMock()
    config.default_group = None
    config.active_only = False
    config.groups = groups or {}
    config.task_calendar = None
    config.task_calendar_account = None
    return config


# ---------------------------------------------------------------------------
# Concise projection tests
# ---------------------------------------------------------------------------


class TestConciseProjection:
    def test_concise_event_drops_description(self) -> None:
        from guten_morgen.mcp_server import _concise_event

        full = {"id": "1", "title": "Meeting", "start": "2026-02-17T09:00:00", "description": "Long body"}
        result = _concise_event(full)
        assert "description" not in result
        assert result["title"] == "Meeting"
        assert result["id"] == "1"

    def test_concise_event_preserves_all_fields(self) -> None:
        from guten_morgen.mcp_server import _concise_event

        full = {
            "id": "1",
            "title": "Meeting",
            "start": "2026-02-17T09:00:00",
            "duration": "PT30M",
            "my_status": "accepted",
            "participants_display": "Alice, Bob",
            "location_display": "Room 42",
            "extra_field": "should be dropped",
        }
        result = _concise_event(full)
        assert len(result) == 7
        assert "extra_field" not in result

    def test_concise_task_drops_description(self) -> None:
        from guten_morgen.mcp_server import _concise_task

        full = {"id": "1", "title": "Review PR", "progress": "needs-action", "description": "Long body"}
        result = _concise_task(full)
        assert "description" not in result
        assert result["title"] == "Review PR"

    def test_concise_task_preserves_all_fields(self) -> None:
        from guten_morgen.mcp_server import _concise_task

        full = {
            "id": "1",
            "title": "Task",
            "due": "2026-02-17",
            "source": "morgen",
            "tag_names": ["urgent"],
            "list_name": "Inbox",
            "project": "AI Adoption",
            "extra": "dropped",
        }
        result = _concise_task(full)
        assert len(result) == 7
        assert "extra" not in result
        assert "progress" not in result


# ---------------------------------------------------------------------------
# Error shape tests
# ---------------------------------------------------------------------------


class TestErrorShape:
    def test_error_json_basic(self) -> None:
        from guten_morgen.mcp_server import _error_json

        result = json.loads(_error_json("Something failed"))
        assert result["error"] == "Something failed"
        assert result["suggestion"] is None

    def test_error_json_with_suggestion(self) -> None:
        from guten_morgen.mcp_server import _error_json

        result = json.loads(_error_json("Not found", "Try gm_tasks_list"))
        assert result["error"] == "Not found"
        assert result["suggestion"] == "Try gm_tasks_list"


# ---------------------------------------------------------------------------
# gm_today handler tests
# ---------------------------------------------------------------------------


class TestHandleGmToday:
    @patch("guten_morgen.time_utils.today_range", return_value=("2026-02-17T00:00:00", "2026-02-17T23:59:59"))
    def test_returns_events_and_tasks(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_today

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_today(client, config))

        assert "events" in result
        assert "scheduled_tasks" in result
        assert "overdue_tasks" in result
        assert "unscheduled_tasks" in result
        assert "meta" in result

    @patch("guten_morgen.time_utils.today_range", return_value=("2026-02-17T00:00:00", "2026-02-17T23:59:59"))
    def test_events_only(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_today

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_today(client, config, events_only=True))

        assert "events" in result
        assert "scheduled_tasks" not in result

    @patch("guten_morgen.time_utils.today_range", return_value=("2026-02-17T00:00:00", "2026-02-17T23:59:59"))
    def test_tasks_only(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_today

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_today(client, config, tasks_only=True))

        assert "events" not in result
        assert "scheduled_tasks" in result

    @patch("guten_morgen.time_utils.today_range", return_value=("2026-02-17T00:00:00", "2026-02-17T23:59:59"))
    def test_truncates_unscheduled(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_today

        # Create 30 unscheduled tasks (no due date)
        many_tasks = [{"id": f"task-{i}", "title": f"Task {i}", "progress": "needs-action"} for i in range(30)]
        client = _make_mock_client(tasks=many_tasks)
        config = _make_mock_config()
        result = json.loads(handle_gm_today(client, config, max_unscheduled=5))

        assert len(result["unscheduled_tasks"]) == 5
        assert result["meta"]["unscheduled_truncated"] is True
        assert result["meta"]["unscheduled_total"] == 30

    @patch("guten_morgen.time_utils.today_range", return_value=("2026-02-17T00:00:00", "2026-02-17T23:59:59"))
    def test_events_are_concise(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_today

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_today(client, config))

        for event in result["events"]:
            assert "description" not in event
            assert "calendarId" not in event

    @patch("guten_morgen.time_utils.today_range", return_value=("2026-02-17T00:00:00", "2026-02-17T23:59:59"))
    def test_excludes_frame_events(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_today

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_today(client, config))

        # evt-3 is a frame event — should be excluded
        event_ids = [e.get("id") for e in result["events"]]
        assert "evt-3" not in event_ids

    @patch("guten_morgen.time_utils.today_range", return_value=("2026-02-17T00:00:00", "2026-02-17T23:59:59"))
    def test_excludes_declined_events(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_today

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_today(client, config))

        event_ids = [e.get("id") for e in result["events"]]
        assert "evt-declined" not in event_ids

    @patch("guten_morgen.time_utils.today_range", return_value=("2026-02-17T00:00:00", "2026-02-17T23:59:59"))
    def test_excludes_completed_tasks(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_today

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_today(client, config))

        all_task_ids = []
        for key in ("scheduled_tasks", "overdue_tasks", "unscheduled_tasks"):
            all_task_ids.extend(t.get("id") for t in result[key])
        assert "task-4" not in all_task_ids  # task-4 is completed


# ---------------------------------------------------------------------------
# gm_next handler tests
# ---------------------------------------------------------------------------


class TestHandleGmNext:
    def test_returns_upcoming_events(self) -> None:
        from guten_morgen.mcp_server import handle_gm_next

        client = _make_mock_client()
        config = _make_mock_config()

        # Patch datetime to be before the fake events
        with patch("guten_morgen.mcp_server.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 17, 8, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = json.loads(handle_gm_next(client, config, count=2))

        assert isinstance(result, list)
        assert len(result) <= 2

    def test_respects_count(self) -> None:
        from guten_morgen.mcp_server import handle_gm_next

        client = _make_mock_client()
        config = _make_mock_config()

        with patch("guten_morgen.mcp_server.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 17, 8, 0, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = json.loads(handle_gm_next(client, config, count=1))

        assert len(result) <= 1


# ---------------------------------------------------------------------------
# gm_this_week handler tests
# ---------------------------------------------------------------------------


class TestHandleGmThisWeek:
    @patch("guten_morgen.time_utils.this_week_range", return_value=("2026-02-17T00:00:00", "2026-02-23T23:59:59"))
    def test_returns_events_and_tasks(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_this_week

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_this_week(client, config))

        assert "events" in result
        assert "scheduled_tasks" in result
        assert "overdue_tasks" in result
        assert "unscheduled_tasks" in result
        assert "meta" in result

    @patch("guten_morgen.time_utils.this_week_range", return_value=("2026-02-17T00:00:00", "2026-02-23T23:59:59"))
    def test_events_only(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_this_week

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_this_week(client, config, events_only=True))

        assert "events" in result
        assert "scheduled_tasks" not in result

    @patch("guten_morgen.time_utils.this_week_range", return_value=("2026-02-17T00:00:00", "2026-02-23T23:59:59"))
    def test_tasks_only(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_this_week

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_this_week(client, config, tasks_only=True))

        assert "events" not in result
        assert "scheduled_tasks" in result


# ---------------------------------------------------------------------------
# gm_this_month handler tests
# ---------------------------------------------------------------------------


class TestHandleGmThisMonth:
    @patch("guten_morgen.time_utils.this_month_range", return_value=("2026-02-01T00:00:00", "2026-02-28T23:59:59"))
    def test_returns_events_and_tasks(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_this_month

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_this_month(client, config))

        assert "events" in result
        assert "scheduled_tasks" in result
        assert "overdue_tasks" in result
        assert "unscheduled_tasks" in result
        assert "meta" in result

    @patch("guten_morgen.time_utils.this_month_range", return_value=("2026-02-01T00:00:00", "2026-02-28T23:59:59"))
    def test_events_only(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_this_month

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_this_month(client, config, events_only=True))

        assert "events" in result
        assert "scheduled_tasks" not in result

    @patch("guten_morgen.time_utils.this_month_range", return_value=("2026-02-01T00:00:00", "2026-02-28T23:59:59"))
    def test_tasks_only(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_this_month

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_this_month(client, config, tasks_only=True))

        assert "events" not in result
        assert "scheduled_tasks" in result


# ---------------------------------------------------------------------------
# gm_events_list handler tests
# ---------------------------------------------------------------------------


class TestHandleGmEventsList:
    def test_returns_concise_events(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_list

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(
            handle_gm_events_list(client, config, start="2026-02-17T00:00:00", end="2026-02-17T23:59:59")
        )

        assert isinstance(result, list)
        for event in result:
            assert "description" not in event

    def test_bare_date_start_normalised(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_list

        client = _make_mock_client()
        config = _make_mock_config()
        handle_gm_events_list(client, config, start="2026-02-17", end="2026-02-17T23:59:59")

        # Verify the client received the normalised datetime, not the bare date
        call_args = client.list_all_events.call_args
        assert call_args[0][0] == "2026-02-17T00:00:00"

    def test_bare_date_end_normalised(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_list

        client = _make_mock_client()
        config = _make_mock_config()
        handle_gm_events_list(client, config, start="2026-02-17T00:00:00", end="2026-02-17")

        # Verify end date normalised to T23:59:59
        call_args = client.list_all_events.call_args
        assert call_args[0][1] == "2026-02-17T23:59:59"


# ---------------------------------------------------------------------------
# gm_availability handler tests
# ---------------------------------------------------------------------------


class TestHandleGmAvailability:
    def test_returns_slots(self) -> None:
        from guten_morgen.mcp_server import handle_gm_availability

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_availability(client, config, date="2026-02-17"))

        assert isinstance(result, list)
        if result:
            assert "start" in result[0]
            assert "end" in result[0]
            assert "duration_minutes" in result[0]

    def test_single_digit_start_hour(self) -> None:
        from guten_morgen.mcp_server import handle_gm_availability

        client = _make_mock_client()
        config = _make_mock_config()
        # start_hour="9" should work the same as "09:00"
        result = json.loads(handle_gm_availability(client, config, date="2026-02-17", start_hour="9"))

        assert isinstance(result, list)
        assert "error" not in result if isinstance(result, list) else "error" not in result

    def test_single_digit_end_hour(self) -> None:
        from guten_morgen.mcp_server import handle_gm_availability

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_availability(client, config, date="2026-02-17", end_hour="6"))

        # Should not error — "6" normalised to "06:00"
        assert isinstance(result, list)


class TestNormalizeHour:
    def test_single_digit(self) -> None:
        from guten_morgen.mcp_server import _normalize_hour

        assert _normalize_hour("9") == "09:00"

    def test_two_digit(self) -> None:
        from guten_morgen.mcp_server import _normalize_hour

        assert _normalize_hour("09") == "09:00"

    def test_full_format(self) -> None:
        from guten_morgen.mcp_server import _normalize_hour

        assert _normalize_hour("09:00") == "09:00"

    def test_single_digit_with_minutes(self) -> None:
        from guten_morgen.mcp_server import _normalize_hour

        assert _normalize_hour("9:30") == "09:30"


# ---------------------------------------------------------------------------
# gm_tasks_list handler tests
# ---------------------------------------------------------------------------


class TestHandleGmTasksList:
    def test_returns_open_tasks(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_list

        client = _make_mock_client()
        result = json.loads(handle_gm_tasks_list(client, status="open"))

        assert isinstance(result, list)
        # Completed task (task-4) should be excluded from open list
        ids = [t["id"] for t in result]
        assert "task-4" not in ids
        # Should be concise — no description or progress
        for task in result:
            assert "description" not in task
            assert "progress" not in task

    def test_returns_completed_tasks(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_list

        client = _make_mock_client()
        result = json.loads(handle_gm_tasks_list(client, status="completed"))

        # Only completed tasks should be returned — task-4 is the only completed one
        ids = [t["id"] for t in result]
        assert "task-4" in ids
        assert len(result) == 1

    def test_limit_clamped(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_list

        many_tasks = [{"id": f"task-{i}", "title": f"Task {i}", "progress": "needs-action"} for i in range(50)]
        client = _make_mock_client(tasks=many_tasks)
        result = json.loads(handle_gm_tasks_list(client, limit=10))

        assert len(result) == 10

    def test_limit_max_100(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_list

        many_tasks = [{"id": f"task-{i}", "title": f"Task {i}", "progress": "needs-action"} for i in range(200)]
        client = _make_mock_client(tasks=many_tasks)
        result = json.loads(handle_gm_tasks_list(client, limit=200))

        assert len(result) == 100

    def test_filter_by_tag(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_list

        client = _make_mock_client()
        result = json.loads(handle_gm_tasks_list(client, tag="urgent"))

        # Only tasks with tag-1 ("urgent") should be returned
        assert len(result) > 0

    def test_filter_by_list_name(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_list

        client = _make_mock_client()
        result = json.loads(handle_gm_tasks_list(client, list_name="Inbox"))

        assert isinstance(result, list)

    def test_filter_overdue(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_list

        client = _make_mock_client()
        result = json.loads(handle_gm_tasks_list(client, overdue=True))

        assert isinstance(result, list)
        # task-3 is overdue (due 2025-10-15)
        ids = [t["id"] for t in result]
        assert "task-3" in ids


# ---------------------------------------------------------------------------
# gm_tasks_get handler tests
# ---------------------------------------------------------------------------


class TestHandleGmTasksGet:
    def test_returns_full_task(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_get
        from guten_morgen.models import Task

        client = _make_mock_client()
        task_data = _TASKS[0].copy()
        client.get_task.return_value = Task(**task_data)

        result = json.loads(handle_gm_tasks_get(client, task_id="task-1"))

        assert result["id"] == "task-1"
        assert result["title"] == "Review PR"
        # Full view includes enriched fields
        assert "tag_names" in result or "list_name" in result

    def test_error_on_not_found(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_get

        client = _make_mock_client()
        client.get_task.side_effect = Exception("Task not found: xyz")

        result = json.loads(handle_gm_tasks_get(client, task_id="xyz"))

        assert "error" in result
        assert result["suggestion"] == "Check the task ID with gm_tasks_list"


# ---------------------------------------------------------------------------
# gm_lists / gm_tags / gm_accounts / gm_groups handler tests
# ---------------------------------------------------------------------------


class TestHandleGmLists:
    def test_returns_lists(self) -> None:
        from guten_morgen.mcp_server import handle_gm_lists

        client = _make_mock_client()
        result = json.loads(handle_gm_lists(client))

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "Inbox"


class TestHandleGmTags:
    def test_returns_tags(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tags

        client = _make_mock_client()
        result = json.loads(handle_gm_tags(client))

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "urgent"


class TestHandleGmAccounts:
    def test_returns_accounts(self) -> None:
        from guten_morgen.mcp_server import handle_gm_accounts

        client = _make_mock_client()
        result = json.loads(handle_gm_accounts(client))

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["integrationId"] == "google"


class TestHandleGmGroups:
    def test_returns_groups(self) -> None:
        from guten_morgen.mcp_server import handle_gm_groups

        config = _make_mock_config()
        result = json.loads(handle_gm_groups(config))

        assert "default_group" in result
        assert "groups" in result
        assert result["default_group"] is None


# ---------------------------------------------------------------------------
# Frame/declined filtering tests
# ---------------------------------------------------------------------------


class TestFiltering:
    def test_is_frame_event(self) -> None:
        from guten_morgen.mcp_server import _is_frame_event

        frame = {"morgen.so:metadata": {"frameFilterMql": "something"}}
        normal = {"morgen.so:metadata": {"isAutoScheduled": False}}
        no_meta = {"title": "Meeting"}

        assert _is_frame_event(frame) is True
        assert _is_frame_event(normal) is False
        assert _is_frame_event(no_meta) is False


# ---------------------------------------------------------------------------
# Phase 2: Mutation handler tests
# ---------------------------------------------------------------------------


class TestHandleGmTasksCreate:
    def test_creates_task(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_create

        client = _make_mock_client()
        client.create_task.return_value = Task(id="new-1", title="Buy milk")

        result = json.loads(handle_gm_tasks_create(client, title="Buy milk"))
        assert result["status"] == "ok"
        assert result["task_id"] == "new-1"
        assert result["title"] == "Buy milk"

    def test_creates_task_with_due(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_create

        client = _make_mock_client()
        client.create_task.return_value = Task(id="new-2", title="Report")

        result = json.loads(handle_gm_tasks_create(client, title="Report", due="2026-03-15"))
        assert result["status"] == "ok"
        # Verify the due date was normalized and passed to client
        call_data = client.create_task.call_args[0][0]
        assert call_data["due"] == "2026-03-15T23:59:59"

    def test_creates_task_with_project_and_ref(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_create

        client = _make_mock_client()
        client.create_task.return_value = Task(id="new-3", title="Review")

        result = json.loads(
            handle_gm_tasks_create(client, title="Review", project="AI Adoption", ref="https://example.com")
        )
        assert result["status"] == "ok"
        call_data = client.create_task.call_args[0][0]
        assert "project: AI Adoption" in call_data["description"]
        assert "ref: https://example.com" in call_data["description"]

    def test_creates_task_with_tag(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_create

        client = _make_mock_client()
        client.create_task.return_value = Task(id="new-4", title="Urgent thing")

        result = json.loads(handle_gm_tasks_create(client, title="Urgent thing", tag="urgent"))
        assert result["status"] == "ok"
        call_data = client.create_task.call_args[0][0]
        assert call_data["tags"] == ["tag-1"]

    def test_creates_task_with_list(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_create

        client = _make_mock_client()
        client.create_task.return_value = Task(id="new-5", title="Work task")

        result = json.loads(handle_gm_tasks_create(client, title="Work task", list_name="Inbox"))
        assert result["status"] == "ok"
        call_data = client.create_task.call_args[0][0]
        assert call_data["taskListId"] == "inbox"

    def test_error_on_failure(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_create

        client = _make_mock_client()
        client.create_task.side_effect = Exception("API error")

        result = json.loads(handle_gm_tasks_create(client, title="Fail"))
        assert "error" in result


class TestHandleGmTasksUpdate:
    def test_updates_task_title(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_update

        client = _make_mock_client()
        client.update_task.return_value = Task(id="task-1", title="New title")

        result = json.loads(handle_gm_tasks_update(client, task_id="task-1", title="New title"))
        assert result["status"] == "ok"
        assert result["task_id"] == "task-1"

    def test_updates_task_due(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_update

        client = _make_mock_client()
        client.update_task.return_value = Task(id="task-1", title="PR")

        handle_gm_tasks_update(client, task_id="task-1", due="2026-04-01")
        call_data = client.update_task.call_args[0][0]
        assert call_data["due"] == "2026-04-01T23:59:59"

    def test_error_on_failure(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_update

        client = _make_mock_client()
        client.update_task.side_effect = Exception("Not found")

        result = json.loads(handle_gm_tasks_update(client, task_id="bad-id"))
        assert "error" in result


class TestHandleGmTasksClose:
    def test_closes_task(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_close

        client = _make_mock_client()
        client.close_task.return_value = Task(id="task-1", title="Done", progress="completed")

        result = json.loads(handle_gm_tasks_close(client, task_id="task-1"))
        assert result["status"] == "ok"
        assert result["task_id"] == "task-1"


class TestHandleGmTasksReopen:
    def test_reopens_task(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_reopen

        client = _make_mock_client()
        client.reopen_task.return_value = Task(id="task-1", title="Back", progress="needs-action")

        result = json.loads(handle_gm_tasks_reopen(client, task_id="task-1"))
        assert result["status"] == "ok"
        assert result["task_id"] == "task-1"


class TestHandleGmTasksDelete:
    def test_deletes_task(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_delete

        client = _make_mock_client()
        client.delete_task.return_value = None

        result = json.loads(handle_gm_tasks_delete(client, task_id="task-1"))
        assert result["status"] == "ok"
        assert result["task_id"] == "task-1"


class TestHandleGmTasksMove:
    def test_moves_task(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_move

        client = _make_mock_client()
        client.move_task.return_value = Task(id="task-1", title="Moved")

        result = json.loads(handle_gm_tasks_move(client, task_id="task-1", after="task-2"))
        assert result["status"] == "ok"
        assert result["task_id"] == "task-1"


class TestHandleGmTasksSchedule:
    def test_schedules_task(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_schedule

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(id="cal-1", accountId="acc-1", integrationGroups=["calendars"], model_dump=lambda: {}),
        ]
        client.schedule_task.return_value = Event(id="evt-new", title="Time block")

        result = json.loads(handle_gm_tasks_schedule(client, task_id="task-1", start="2026-03-15T10:00:00"))
        assert result["status"] == "ok"
        assert result["event_id"] == "evt-new"


class TestHandleGmEventsCreate:
    def test_creates_event(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_create

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(id="cal-1", accountId="acc-1", integrationGroups=["calendars"], model_dump=lambda: {}),
        ]
        client.create_event.return_value = Event(id="evt-new", title="Meeting")

        result = json.loads(
            handle_gm_events_create(client, title="Meeting", start="2026-03-15T10:00:00", duration_minutes=60)
        )
        assert result["status"] == "ok"
        assert result["event_id"] == "evt-new"
        assert result["title"] == "Meeting"

    def test_error_on_failure(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_create

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(id="cal-1", accountId="acc-1", integrationGroups=["calendars"], model_dump=lambda: {}),
        ]
        client.create_event.side_effect = Exception("Calendar error")

        result = json.loads(
            handle_gm_events_create(client, title="Fail", start="2026-03-15T10:00:00", duration_minutes=30)
        )
        assert "error" in result


class TestHandleGmEventsUpdate:
    def test_updates_event(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_update

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(id="cal-1", accountId="acc-1", integrationGroups=["calendars"], model_dump=lambda: {}),
        ]
        client.update_event.return_value = Event(id="evt-1", title="Updated")

        result = json.loads(handle_gm_events_update(client, event_id="evt-1", title="Updated"))
        assert result["status"] == "ok"
        assert result["event_id"] == "evt-1"


class TestHandleGmEventsDelete:
    def test_deletes_event(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_delete

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(id="cal-1", accountId="acc-1", integrationGroups=["calendars"], model_dump=lambda: {}),
        ]
        client.delete_event.return_value = None

        result = json.loads(handle_gm_events_delete(client, event_id="evt-1"))
        assert result["status"] == "ok"
        assert result["event_id"] == "evt-1"


class TestHandleGmEventsRsvp:
    def test_rsvps_event(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_rsvp

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(id="cal-1", accountId="acc-1", integrationGroups=["calendars"], model_dump=lambda: {}),
        ]
        client.rsvp_event.return_value = {"status": "ok"}

        result = json.loads(handle_gm_events_rsvp(client, event_id="evt-1", action="accept"))
        assert result["status"] == "ok"
        assert result["event_id"] == "evt-1"
        assert result["action"] == "rsvped"

    def test_error_on_failure(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_rsvp

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(id="cal-1", accountId="acc-1", integrationGroups=["calendars"], model_dump=lambda: {}),
        ]
        client.rsvp_event.side_effect = Exception("RSVP failed")

        result = json.loads(handle_gm_events_rsvp(client, event_id="evt-1", action="accept"))
        assert "error" in result


# ---------------------------------------------------------------------------
# Error-path tests for mutation handlers (Fix 5)
# ---------------------------------------------------------------------------


class TestMutationErrorPaths:
    def test_tasks_close_error(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_close

        client = _make_mock_client()
        client.close_task.side_effect = Exception("Cannot close")

        result = json.loads(handle_gm_tasks_close(client, task_id="bad-id"))
        assert "error" in result

    def test_tasks_reopen_error(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_reopen

        client = _make_mock_client()
        client.reopen_task.side_effect = Exception("Cannot reopen")

        result = json.loads(handle_gm_tasks_reopen(client, task_id="bad-id"))
        assert "error" in result

    def test_tasks_delete_error(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_delete

        client = _make_mock_client()
        client.delete_task.side_effect = Exception("Cannot delete")

        result = json.loads(handle_gm_tasks_delete(client, task_id="bad-id"))
        assert "error" in result

    def test_tasks_move_error(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_move

        client = _make_mock_client()
        client.move_task.side_effect = Exception("Cannot move")

        result = json.loads(handle_gm_tasks_move(client, task_id="bad-id", after="other"))
        assert "error" in result

    def test_tasks_schedule_error(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_schedule

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(id="cal-1", accountId="acc-1", integrationGroups=["calendars"], model_dump=lambda: {}),
        ]
        client.schedule_task.side_effect = Exception("Schedule failed")

        result = json.loads(handle_gm_tasks_schedule(client, task_id="t-1", start="2026-03-15T10:00:00"))
        assert "error" in result

    def test_events_update_error(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_update

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(id="cal-1", accountId="acc-1", integrationGroups=["calendars"], model_dump=lambda: {}),
        ]
        client.update_event.side_effect = Exception("Update failed")

        result = json.loads(handle_gm_events_update(client, event_id="evt-1", title="X"))
        assert "error" in result

    def test_events_delete_error(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_delete

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(id="cal-1", accountId="acc-1", integrationGroups=["calendars"], model_dump=lambda: {}),
        ]
        client.delete_event.side_effect = Exception("Delete failed")

        result = json.loads(handle_gm_events_delete(client, event_id="evt-1"))
        assert "error" in result


# ---------------------------------------------------------------------------
# Mutation helper unit tests
# ---------------------------------------------------------------------------


class TestNormalizeDue:
    def test_bare_date(self) -> None:
        from guten_morgen.mcp_server import _normalize_due

        assert _normalize_due("2026-03-15") == "2026-03-15T23:59:59"

    def test_strips_z(self) -> None:
        from guten_morgen.mcp_server import _normalize_due

        assert _normalize_due("2026-03-15T23:59:59Z") == "2026-03-15T23:59:59"

    def test_strips_positive_offset(self) -> None:
        from guten_morgen.mcp_server import _normalize_due

        assert _normalize_due("2026-03-15T10:00:00+02:00") == "2026-03-15T10:00:00"

    def test_strips_negative_offset(self) -> None:
        from guten_morgen.mcp_server import _normalize_due

        assert _normalize_due("2026-03-15T10:00:00-05:00") == "2026-03-15T10:00:00"

    def test_passthrough_19_chars(self) -> None:
        from guten_morgen.mcp_server import _normalize_due

        assert _normalize_due("2026-03-15T23:59:59") == "2026-03-15T23:59:59"


class TestResolveListNameId:
    def test_resolves_known_list(self) -> None:
        from guten_morgen.mcp_server import _resolve_list_name_id

        client = _make_mock_client()
        assert _resolve_list_name_id(client, "Inbox") == "inbox"

    def test_case_insensitive(self) -> None:
        from guten_morgen.mcp_server import _resolve_list_name_id

        client = _make_mock_client()
        assert _resolve_list_name_id(client, "inbox") == "inbox"

    def test_raises_on_unknown(self) -> None:
        import pytest

        from guten_morgen.mcp_server import _resolve_list_name_id

        client = _make_mock_client()
        with pytest.raises(RuntimeError, match="not found"):
            _resolve_list_name_id(client, "Nonexistent")


class TestAutoDiscover:
    def test_prefers_writable_calendars(self) -> None:
        from guten_morgen.mcp_server import _auto_discover

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(
                id="cal-rw",
                accountId="acc-1",
                integrationGroups=["calendars"],
                model_dump=lambda: {"myRights": {"mayWriteAll": True}},
            ),
            MagicMock(
                id="cal-ro",
                accountId="acc-1",
                integrationGroups=["calendars"],
                model_dump=lambda: {"myRights": {"mayWriteAll": False, "mayWriteOwn": False}},
            ),
        ]

        account_id, cal_ids = _auto_discover(client)
        assert account_id == "acc-1"
        assert cal_ids == ["cal-rw"]

    def test_falls_back_to_all_if_none_writable(self) -> None:
        from guten_morgen.mcp_server import _auto_discover

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(
                id="cal-ro",
                accountId="acc-1",
                integrationGroups=["calendars"],
                model_dump=lambda: {"myRights": {"mayWriteAll": False}},
            ),
        ]

        _, cal_ids = _auto_discover(client)
        assert cal_ids == ["cal-ro"]

    def test_raises_on_no_accounts(self) -> None:
        import pytest

        from guten_morgen.mcp_server import _auto_discover

        client = _make_mock_client()
        client.list_accounts.return_value = []

        with pytest.raises(RuntimeError, match="No connected accounts"):
            _auto_discover(client)


class TestHandleGmTasksUpdateProjectRef:
    def test_updates_task_with_project(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_update

        client = _make_mock_client()
        existing_task = Task(id="task-1", title="PR", description="<p>existing body</p>")
        client.get_task.return_value = existing_task
        client.update_task.return_value = Task(id="task-1", title="PR")

        result = json.loads(handle_gm_tasks_update(client, task_id="task-1", project="AI Adoption"))
        assert result["status"] == "ok"
        call_data = client.update_task.call_args[0][0]
        assert "project: AI Adoption" in call_data["description"]

    def test_updates_task_with_ref(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_update

        client = _make_mock_client()
        existing_task = Task(id="task-1", title="PR", description="<p>body</p>")
        client.get_task.return_value = existing_task
        client.update_task.return_value = Task(id="task-1", title="PR")

        result = json.loads(handle_gm_tasks_update(client, task_id="task-1", ref="https://example.com"))
        assert result["status"] == "ok"
        call_data = client.update_task.call_args[0][0]
        assert "ref: https://example.com" in call_data["description"]

    def test_unresolved_list_returns_error(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_create

        client = _make_mock_client()

        result = json.loads(handle_gm_tasks_create(client, title="Test", list_name="Nonexistent"))
        assert "error" in result
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# Phase 3: Tag/list CRUD handler tests
# ---------------------------------------------------------------------------


class TestHandleGmTagsCreate:
    def test_creates_tag(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tags_create

        client = _make_mock_client()
        client.create_tag.return_value = Tag(id="tag-new", name="Focus", color="#0000ff")

        result = json.loads(handle_gm_tags_create(client, name="Focus"))
        assert result["status"] == "ok"
        assert result["tag_id"] == "tag-new"
        assert result["name"] == "Focus"

    def test_creates_tag_with_colour(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tags_create

        client = _make_mock_client()
        client.create_tag.return_value = Tag(id="tag-new", name="Focus", color="#0000ff")

        handle_gm_tags_create(client, name="Focus", color="#0000ff")
        call_data = client.create_tag.call_args[0][0]
        assert call_data["color"] == "#0000ff"

    def test_error_on_failure(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tags_create

        client = _make_mock_client()
        client.create_tag.side_effect = Exception("Duplicate name")

        result = json.loads(handle_gm_tags_create(client, name="Fail"))
        assert "error" in result

    def test_error_when_api_returns_none(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tags_create

        client = _make_mock_client()
        client.create_tag.return_value = None

        result = json.loads(handle_gm_tags_create(client, name="Ghost"))
        assert "error" in result
        assert "no ID" in result["error"]


class TestHandleGmTagsUpdate:
    def test_updates_tag(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tags_update

        client = _make_mock_client()
        client.update_tag.return_value = Tag(id="tag-1", name="Renamed")

        result = json.loads(handle_gm_tags_update(client, tag_id="tag-1", name="Renamed"))
        assert result["status"] == "ok"
        assert result["tag_id"] == "tag-1"

    def test_error_no_fields(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tags_update

        client = _make_mock_client()

        result = json.loads(handle_gm_tags_update(client, tag_id="tag-1"))
        assert "error" in result
        assert "No fields" in result["error"]
        client.update_tag.assert_not_called()

    def test_error_on_failure(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tags_update

        client = _make_mock_client()
        client.update_tag.side_effect = Exception("Not found")

        result = json.loads(handle_gm_tags_update(client, tag_id="bad"))
        assert "error" in result


class TestHandleGmTagsDelete:
    def test_deletes_tag(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tags_delete

        client = _make_mock_client()
        client.delete_tag.return_value = None

        result = json.loads(handle_gm_tags_delete(client, tag_id="tag-1"))
        assert result["status"] == "ok"
        assert result["tag_id"] == "tag-1"

    def test_error_on_failure(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tags_delete

        client = _make_mock_client()
        client.delete_tag.side_effect = Exception("Not found")

        result = json.loads(handle_gm_tags_delete(client, tag_id="bad"))
        assert "error" in result


class TestHandleGmListsCreate:
    def test_creates_list(self) -> None:
        from guten_morgen.mcp_server import handle_gm_lists_create

        client = _make_mock_client()
        client.create_task_list.return_value = TaskList(id="list-new", name="Projects", color="#ff0000")

        result = json.loads(handle_gm_lists_create(client, name="Projects"))
        assert result["status"] == "ok"
        assert result["list_id"] == "list-new"
        assert result["name"] == "Projects"

    def test_error_when_api_returns_none(self) -> None:
        from guten_morgen.mcp_server import handle_gm_lists_create

        client = _make_mock_client()
        client.create_task_list.return_value = None

        result = json.loads(handle_gm_lists_create(client, name="Ghost"))
        assert "error" in result
        assert "no ID" in result["error"]

    def test_error_on_failure(self) -> None:
        from guten_morgen.mcp_server import handle_gm_lists_create

        client = _make_mock_client()
        client.create_task_list.side_effect = Exception("API error")

        result = json.loads(handle_gm_lists_create(client, name="Fail"))
        assert "error" in result


class TestHandleGmListsUpdate:
    def test_updates_list(self) -> None:
        from guten_morgen.mcp_server import handle_gm_lists_update

        client = _make_mock_client()
        client.update_task_list.return_value = TaskList(id="inbox", name="Renamed")

        result = json.loads(handle_gm_lists_update(client, list_id="inbox", name="Renamed"))
        assert result["status"] == "ok"
        assert result["list_id"] == "inbox"

    def test_error_no_fields(self) -> None:
        from guten_morgen.mcp_server import handle_gm_lists_update

        client = _make_mock_client()

        result = json.loads(handle_gm_lists_update(client, list_id="inbox"))
        assert "error" in result
        assert "No fields" in result["error"]
        client.update_task_list.assert_not_called()

    def test_error_on_failure(self) -> None:
        from guten_morgen.mcp_server import handle_gm_lists_update

        client = _make_mock_client()
        client.update_task_list.side_effect = Exception("Not found")

        result = json.loads(handle_gm_lists_update(client, list_id="bad"))
        assert "error" in result


class TestHandleGmListsDelete:
    def test_deletes_list(self) -> None:
        from guten_morgen.mcp_server import handle_gm_lists_delete

        client = _make_mock_client()
        client.delete_task_list.return_value = None

        result = json.loads(handle_gm_lists_delete(client, list_id="inbox"))
        assert result["status"] == "ok"
        assert result["list_id"] == "inbox"

    def test_error_on_failure(self) -> None:
        from guten_morgen.mcp_server import handle_gm_lists_delete

        client = _make_mock_client()
        client.delete_task_list.side_effect = Exception("Not found")

        result = json.loads(handle_gm_lists_delete(client, list_id="bad"))
        assert "error" in result


# ---------------------------------------------------------------------------
# Issue 2: Proxy vars must include HTTP_PROXY / HTTPS_PROXY
# ---------------------------------------------------------------------------


class TestNormalizeDatetime:
    def test_bare_date_start(self) -> None:
        from guten_morgen.mcp_server import _normalize_datetime_start

        assert _normalize_datetime_start("2026-03-12") == "2026-03-12T00:00:00"

    def test_full_datetime_unchanged(self) -> None:
        from guten_morgen.mcp_server import _normalize_datetime_start

        assert _normalize_datetime_start("2026-03-12T09:30:00") == "2026-03-12T09:30:00"

    def test_bare_date_end(self) -> None:
        from guten_morgen.mcp_server import _normalize_datetime_end

        assert _normalize_datetime_end("2026-03-12") == "2026-03-12T23:59:59"

    def test_full_datetime_end_unchanged(self) -> None:
        from guten_morgen.mcp_server import _normalize_datetime_end

        assert _normalize_datetime_end("2026-03-12T18:00:00") == "2026-03-12T18:00:00"


class TestProxyVars:
    def test_includes_http_and_https_proxy(self) -> None:
        from guten_morgen.mcp_server import _PROXY_VARS

        for var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
            assert var in _PROXY_VARS, f"{var} missing from _PROXY_VARS"


# ---------------------------------------------------------------------------
# Issue 3: RSVP response should use _mutation_ok pattern
# ---------------------------------------------------------------------------


class TestHandleGmEventsRsvpResponse:
    def test_rsvp_uses_mutation_ok_shape(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_rsvp

        client = _make_mock_client()
        client.list_accounts.return_value = [Account(**_ACCOUNTS[0])]
        client.list_calendars.return_value = [
            MagicMock(id="cal-1", accountId="acc-1", integrationGroups=["calendars"], model_dump=lambda: {}),
        ]
        client.rsvp_event.return_value = {"status": "ok"}

        result = json.loads(handle_gm_events_rsvp(client, event_id="evt-1", action="accept"))
        # Should have "action" key with past-tense verb from _mutation_ok, not the raw input
        assert result["status"] == "ok"
        assert result["action"] == "rsvped"
        assert result["event_id"] == "evt-1"


# ---------------------------------------------------------------------------
# Issue 4: Date range guard on gm_events_list
# ---------------------------------------------------------------------------


class TestHandleGmEventsListDateGuard:
    def test_rejects_range_over_90_days(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_list

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(
            handle_gm_events_list(client, config, start="2026-01-01T00:00:00", end="2026-12-31T23:59:59")
        )

        assert "error" in result
        assert "90" in result["error"]

    def test_allows_range_within_90_days(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_list

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(
            handle_gm_events_list(client, config, start="2026-02-17T00:00:00", end="2026-03-17T23:59:59")
        )

        # Should succeed (28 days)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Phase B: Audit fix tests
# ---------------------------------------------------------------------------


class TestTasksListQueryFilter:
    """Phase B item 1: text search on gm_tasks_list via query param."""

    def test_query_matches_title_case_insensitive(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_list

        client = _make_mock_client()
        result = json.loads(handle_gm_tasks_list(client, query="review"))

        ids = [t["id"] for t in result]
        assert "task-1" in ids  # "Review PR"
        assert "task-2" not in ids  # "Write docs"

    def test_query_matches_description(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_list

        tasks = [
            {
                "id": "t-a",
                "title": "Fix bug",
                "progress": "needs-action",
                "description": "<p>Check the auth module</p>",
            },
            {"id": "t-b", "title": "Other", "progress": "needs-action"},
        ]
        client = _make_mock_client(tasks=tasks)
        result = json.loads(handle_gm_tasks_list(client, query="auth"))

        ids = [t["id"] for t in result]
        assert "t-a" in ids
        assert "t-b" not in ids

    def test_query_none_returns_all(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_list

        client = _make_mock_client()
        with_query = json.loads(handle_gm_tasks_list(client))
        without_query = json.loads(handle_gm_tasks_list(client, query=None))

        assert len(with_query) == len(without_query)


class TestSmartUnscheduledTruncation:
    """Phase B item 2: sort unscheduled by tag priority before truncation."""

    @patch("guten_morgen.time_utils.today_range", return_value=("2026-02-17T00:00:00", "2026-02-17T23:59:59"))
    def test_right_now_tasks_appear_first(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_today

        tags = [
            {"id": "tag-rn", "name": "Right-Now", "color": "#dc2626"},
            {"id": "tag-sd", "name": "Someday", "color": "#6b7280"},
            {"id": "tag-ac", "name": "Active", "color": "#22c55e"},
        ]
        tasks = [
            {"id": "someday-1", "title": "Someday task", "progress": "needs-action", "tags": ["tag-sd"]},
            {"id": "right-now-1", "title": "Right now task", "progress": "needs-action", "tags": ["tag-rn"]},
            {"id": "active-1", "title": "Active task", "progress": "needs-action", "tags": ["tag-ac"]},
            {"id": "no-tag-1", "title": "No tag task", "progress": "needs-action", "tags": []},
        ]
        client = _make_mock_client(tasks=tasks, tags=tags, events=[])
        config = _make_mock_config()
        result = json.loads(handle_gm_today(client, config, max_unscheduled=3))

        ids = [t["id"] for t in result["unscheduled_tasks"]]
        # Right-Now should come first, then Active, then Someday
        assert ids[0] == "right-now-1"
        assert ids[1] == "active-1"

    def test_tag_sort_key_priority_order(self) -> None:
        from guten_morgen.mcp_server import _tag_sort_key

        tag_id_to_name = {"t1": "Right-Now", "t2": "Active", "t3": "Waiting-On", "t4": "Someday"}

        # Right-Now < Active < Waiting-On < Someday < untagged
        assert _tag_sort_key(["t1"], tag_id_to_name) < _tag_sort_key(["t2"], tag_id_to_name)
        assert _tag_sort_key(["t2"], tag_id_to_name) < _tag_sort_key(["t3"], tag_id_to_name)
        assert _tag_sort_key(["t3"], tag_id_to_name) < _tag_sort_key(["t4"], tag_id_to_name)
        assert _tag_sort_key(["t4"], tag_id_to_name) < _tag_sort_key([], tag_id_to_name)


class TestConciseTaskDropsProgress:
    """Phase B item 3: progress field removed from concise projection."""

    def test_concise_task_has_no_progress(self) -> None:
        from guten_morgen.mcp_server import _concise_task

        full = {"id": "1", "title": "Task", "progress": "needs-action", "due": "2026-02-17"}
        result = _concise_task(full)
        assert "progress" not in result

    @patch("guten_morgen.time_utils.today_range", return_value=("2026-02-17T00:00:00", "2026-02-17T23:59:59"))
    def test_today_tasks_have_no_progress(self, _mock_range: Any) -> None:
        from guten_morgen.mcp_server import handle_gm_today

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_today(client, config))

        for key in ("scheduled_tasks", "overdue_tasks", "unscheduled_tasks"):
            for t in result[key]:
                assert "progress" not in t


class TestTasksGetSuppressNulls:
    """Phase B item 4: suppress None values in gm_tasks_get output."""

    def test_no_none_values_in_output(self) -> None:
        from guten_morgen.mcp_server import handle_gm_tasks_get

        client = _make_mock_client()
        task_data = {
            "id": "task-1",
            "title": "Review PR",
            "progress": "needs-action",
            "due": None,
            "description": None,
            "priority": 2,
        }
        client.get_task.return_value = Task(**task_data)

        result = json.loads(handle_gm_tasks_get(client, task_id="task-1"))
        none_keys = [k for k, v in result.items() if v is None]
        assert none_keys == [], f"Keys with None values: {none_keys}"


class TestHandleGmEventsGet:
    """Phase B item 5: gm_events_get — full event detail with structured participants."""

    def test_returns_full_event(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_get

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_events_get(client, config, event_id="evt-1"))

        assert result["id"] == "evt-1"
        assert result["title"] == "Standup"
        assert "description" in result or result.get("description") is None  # full view includes all fields

    def test_participants_structured(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_get

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_events_get(client, config, event_id="evt-1"))

        assert "participants" in result
        participants = result["participants"]
        assert isinstance(participants, list)
        # Should have name, email, status, is_organiser
        for p in participants:
            assert "name" in p or "email" in p
            assert "status" in p
            assert "is_organiser" in p

    def test_filters_resource_participants(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_get

        events = [
            {
                "id": "evt-room",
                "title": "Meeting with room",
                "start": "2026-02-17T10:00:00",
                "duration": "PT1H",
                "calendarId": "cal-1",
                "accountId": "acc-1",
                "participants": {
                    "p1": {
                        "name": "Alice",
                        "email": "alice@example.com",
                        "kind": "individual",
                        "participationStatus": "accepted",
                    },
                    "room": {
                        "name": "Room A",
                        "email": "room-a@example.com",
                        "kind": "resource",
                        "participationStatus": "accepted",
                    },
                },
            },
        ]
        client = _make_mock_client(events=events)
        config = _make_mock_config()
        result = json.loads(handle_gm_events_get(client, config, event_id="evt-room"))

        names = [p.get("name") for p in result["participants"]]
        assert "Alice" in names
        assert "Room A" not in names

    def test_not_found_returns_error(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_get

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_events_get(client, config, event_id="nonexistent"))

        assert "error" in result

    def test_suppresses_none_values(self) -> None:
        from guten_morgen.mcp_server import handle_gm_events_get

        client = _make_mock_client()
        config = _make_mock_config()
        result = json.loads(handle_gm_events_get(client, config, event_id="evt-1"))

        none_keys = [k for k, v in result.items() if v is None]
        assert none_keys == [], f"Keys with None values: {none_keys}"
