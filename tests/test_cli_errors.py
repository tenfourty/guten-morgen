"""Tests for error handling paths across CLI commands."""

from __future__ import annotations

import json
from unittest.mock import patch

from click.testing import CliRunner

from morgen.cli import cli
from morgen.errors import AuthenticationError, MorgenAPIError, NotFoundError, RateLimitError


class TestErrorHandling:
    """Error handling paths output structured JSON errors to stderr."""

    def _assert_structured_error(self, result, error_type: str) -> None:
        """Assert exit code 1 and structured error JSON on stderr."""
        assert result.exit_code == 1
        err = json.loads(result.output)
        assert err["error"]["type"] == error_type
        assert "message" in err["error"]

    def test_accounts_auth_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "list_accounts", side_effect=AuthenticationError("Invalid API key")):
            result = runner.invoke(cli, ["accounts", "--json"], catch_exceptions=False)
        self._assert_structured_error(result, "authentication_error")

    def test_calendars_auth_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "list_calendars", side_effect=AuthenticationError("Invalid API key")):
            result = runner.invoke(cli, ["calendars", "--json"], catch_exceptions=False)
        self._assert_structured_error(result, "authentication_error")

    def test_events_list_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "list_all_events", side_effect=MorgenAPIError("API error 500: Internal")):
            result = runner.invoke(
                cli,
                ["events", "list", "--start", "2026-02-17", "--end", "2026-02-18", "--json"],
                catch_exceptions=False,
            )
        self._assert_structured_error(result, "api_error")

    def test_events_create_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "create_event", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(
                cli,
                ["events", "create", "--title", "Test", "--start", "2026-02-17T09:00:00", "--duration", "30"],
                catch_exceptions=False,
            )
        self._assert_structured_error(result, "api_error")

    def test_events_update_not_found(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "update_event", side_effect=NotFoundError("Not found")):
            result = runner.invoke(
                cli,
                ["events", "update", "evt-999", "--title", "Updated"],
                catch_exceptions=False,
            )
        self._assert_structured_error(result, "not_found")

    def test_events_delete_not_found(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "delete_event", side_effect=NotFoundError("Not found")):
            result = runner.invoke(cli, ["events", "delete", "evt-999"], catch_exceptions=False)
        self._assert_structured_error(result, "not_found")

    def test_tasks_list_rate_limit(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "list_all_tasks", side_effect=RateLimitError("Rate limit exceeded")):
            result = runner.invoke(cli, ["tasks", "list", "--json"], catch_exceptions=False)
        self._assert_structured_error(result, "rate_limit_error")
        err = json.loads(result.output)
        assert "suggestions" in err["error"]

    def test_tasks_get_not_found(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "get_task", side_effect=NotFoundError("Task not found")):
            result = runner.invoke(cli, ["tasks", "get", "task-999", "--json"], catch_exceptions=False)
        self._assert_structured_error(result, "not_found")

    def test_tasks_create_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "create_task", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(cli, ["tasks", "create", "--title", "New Task"], catch_exceptions=False)
        self._assert_structured_error(result, "api_error")

    def test_tasks_update_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "update_task", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(cli, ["tasks", "update", "task-1", "--title", "Updated"], catch_exceptions=False)
        self._assert_structured_error(result, "api_error")

    def test_tasks_close_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "close_task", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(cli, ["tasks", "close", "task-1"], catch_exceptions=False)
        self._assert_structured_error(result, "api_error")

    def test_tasks_reopen_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "reopen_task", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(cli, ["tasks", "reopen", "task-1"], catch_exceptions=False)
        self._assert_structured_error(result, "api_error")

    def test_tasks_move_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "move_task", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(cli, ["tasks", "move", "task-1", "--after", "task-2"], catch_exceptions=False)
        self._assert_structured_error(result, "api_error")

    def test_tasks_delete_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "delete_task", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(cli, ["tasks", "delete", "task-1"], catch_exceptions=False)
        self._assert_structured_error(result, "api_error")

    def test_tags_list_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "list_tags", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(cli, ["tags", "list", "--json"], catch_exceptions=False)
        self._assert_structured_error(result, "api_error")

    def test_tags_get_not_found(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "get_tag", side_effect=NotFoundError("Tag not found")):
            result = runner.invoke(cli, ["tags", "get", "tag-999", "--json"], catch_exceptions=False)
        self._assert_structured_error(result, "not_found")

    def test_tags_create_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "create_tag", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(cli, ["tags", "create", "--name", "test"], catch_exceptions=False)
        self._assert_structured_error(result, "api_error")

    def test_tags_update_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "update_tag", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(cli, ["tags", "update", "tag-1", "--name", "updated"], catch_exceptions=False)
        self._assert_structured_error(result, "api_error")

    def test_tags_delete_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "delete_tag", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(cli, ["tags", "delete", "tag-1"], catch_exceptions=False)
        self._assert_structured_error(result, "api_error")

    def test_next_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "list_all_events", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(cli, ["next", "--json"], catch_exceptions=False)
        self._assert_structured_error(result, "api_error")

    def test_today_api_error(self, runner: CliRunner, mock_client) -> None:
        with patch.object(mock_client, "list_all_events", side_effect=MorgenAPIError("API error 500")):
            result = runner.invoke(cli, ["today", "--json"], catch_exceptions=False)
        self._assert_structured_error(result, "api_error")

    def test_error_with_suggestions(self, runner: CliRunner, mock_client) -> None:
        with patch.object(
            mock_client,
            "list_accounts",
            side_effect=AuthenticationError("Invalid API key"),
        ):
            result = runner.invoke(cli, ["accounts", "--json"], catch_exceptions=False)
        err = json.loads(result.output)
        assert "suggestions" in err["error"]
        assert any("MORGEN_API_KEY" in s for s in err["error"]["suggestions"])
