"""Tests for multi-source task client methods."""

from __future__ import annotations

import json

import httpx

from guten_morgen.client import MorgenClient
from guten_morgen.config import Settings


class TestListTaskAccounts:
    def test_returns_only_task_accounts(self, client: MorgenClient) -> None:
        accounts = client.list_task_accounts()
        integration_ids = [a.integrationId for a in accounts]
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
        sources = {t.integrationId for t in result.tasks}
        assert "morgen" in sources
        assert "linear" in sources
        assert "notion" in sources

    def test_includes_label_defs(self, client: MorgenClient) -> None:
        result = client.list_all_tasks()
        assert len(result.labelDefs) > 0

    def test_source_filter(self, client: MorgenClient) -> None:
        result = client.list_all_tasks(source="linear")
        sources = {t.integrationId for t in result.tasks}
        assert sources == {"linear"}

    def test_morgen_only(self, client: MorgenClient) -> None:
        result = client.list_all_tasks(source="morgen")
        sources = {t.integrationId for t in result.tasks}
        assert sources == {"morgen"}


class TestListAllTasksAccountFailure:
    """list_all_tasks skips external accounts that return errors (e.g. disconnected)."""

    @staticmethod
    def _make_client_with_dead_account() -> MorgenClient:
        """Build a client where Notion account returns 404 (disconnected)."""
        from tests.conftest import (
            ALL_ACCOUNTS,
            FAKE_LINEAR_TASKS,
            FAKE_TASKS,
        )

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/v3/integrations/accounts/list":
                return httpx.Response(200, json={"data": {"accounts": ALL_ACCOUNTS}})
            if path == "/v3/tasks/list":
                account_id = dict(request.url.params).get("accountId")
                if account_id is None:
                    # Morgen-native tasks
                    return httpx.Response(200, json={"data": {"tasks": FAKE_TASKS}})
                if account_id == "acc-linear":
                    return httpx.Response(200, json=FAKE_LINEAR_TASKS)
                if account_id == "acc-notion":
                    # Disconnected account — Morgen returns 404
                    return httpx.Response(
                        404,
                        json={"message": "Account not found", "status": 404},
                    )
            return httpx.Response(404)

        settings = Settings(api_key="test-key")
        return MorgenClient(settings, transport=httpx.MockTransport(handler))

    def test_skips_disconnected_account(self) -> None:
        """A 404 from one external account should not kill the whole task listing."""
        client = self._make_client_with_dead_account()
        result = client.list_all_tasks()
        sources = {t.integrationId for t in result.tasks}
        # Morgen and Linear should still be present
        assert "morgen" in sources
        assert "linear" in sources
        # Notion was disconnected — its tasks are absent, but no crash
        assert "notion" not in sources

    def test_skips_disconnected_account_returns_other_label_defs(self) -> None:
        """Label defs from working accounts should still be returned."""
        client = self._make_client_with_dead_account()
        result = client.list_all_tasks()
        # Linear labelDefs should still be present
        assert len(result.labelDefs) > 0


class TestScheduleTask:
    """Task 9: schedule_task() creates a linked event from a task."""

    @staticmethod
    def _make_client(task_data: dict[str, object]) -> MorgenClient:
        """Build a client with a mock that returns task_data for GET and echoes POST."""
        requests_log: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests_log.append(request)
            if request.url.path.rstrip("/") == "/v3/tasks" and request.method == "GET":
                return httpx.Response(200, json={"data": {"task": task_data}})
            if request.url.path == "/v3/events/create" and request.method == "POST":
                body = json.loads(request.content)
                body.setdefault("id", "evt-new")
                return httpx.Response(200, json={"data": {"event": body}})
            return httpx.Response(404)

        settings = Settings(api_key="test-key")
        client = MorgenClient(settings, transport=httpx.MockTransport(handler))
        client._requests_log = requests_log  # type: ignore[attr-defined]
        return client

    def test_creates_event_from_task(self) -> None:
        """schedule_task fetches task, creates event with linked metadata."""
        client = self._make_client({"id": "task-1", "title": "Review PR", "estimatedDuration": "PT30M"})
        result = client.schedule_task(
            task_id="task-1",
            start="2026-02-18T09:00:00",
            calendar_id="cal-1",
            account_id="acc-1",
        )
        assert result is not None
        assert result.title == "Review PR"
        assert result.duration == "PT30M"
        assert result.calendarId == "cal-1"
        # Verify morgen.so:metadata links to the task
        assert result.morgen_metadata is not None
        assert result.morgen_metadata.get("taskId") == "task-1"

    def test_uses_default_duration(self) -> None:
        """When task has no estimatedDuration, default to PT30M."""
        client = self._make_client({"id": "task-2", "title": "Quick task"})
        result = client.schedule_task(
            task_id="task-2",
            start="2026-02-18T10:00:00",
            calendar_id="cal-1",
            account_id="acc-1",
        )
        assert result is not None
        assert result.duration == "PT30M"

    def test_duration_override(self) -> None:
        """Explicit duration_minutes overrides task's estimatedDuration."""
        client = self._make_client({"id": "task-1", "title": "Long task", "estimatedDuration": "PT30M"})
        result = client.schedule_task(
            task_id="task-1",
            start="2026-02-18T09:00:00",
            calendar_id="cal-1",
            account_id="acc-1",
            duration_minutes=60,
        )
        assert result is not None
        assert result.duration == "PT60M"
