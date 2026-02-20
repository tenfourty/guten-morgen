"""Tests for error handling paths across CLI commands."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.errors import AuthenticationError, MorgenAPIError, NotFoundError, RateLimitError

_ERR = MorgenAPIError("API error 500")

_ERROR_CASES: list[tuple[str, Exception, list[str], str]] = [
    # Accounts & calendars
    ("list_accounts", AuthenticationError("msg"), ["accounts", "--json"], "authentication_error"),
    ("list_calendars", AuthenticationError("msg"), ["calendars", "list", "--json"], "authentication_error"),
    # Events
    (
        "list_all_events",
        MorgenAPIError("500"),
        ["events", "list", "--start", "2026-02-17", "--end", "2026-02-18", "--json"],
        "api_error",
    ),
    (
        "create_event",
        _ERR,
        ["events", "create", "--title", "Test", "--start", "2026-02-17T09:00:00", "--duration", "30"],
        "api_error",
    ),
    ("update_event", NotFoundError("Not found"), ["events", "update", "evt-999", "--title", "Updated"], "not_found"),
    ("delete_event", NotFoundError("Not found"), ["events", "delete", "evt-999"], "not_found"),
    # Tasks
    ("get_task", NotFoundError("Not found"), ["tasks", "get", "task-999", "--json"], "not_found"),
    ("create_task", _ERR, ["tasks", "create", "--title", "New Task"], "api_error"),
    ("update_task", _ERR, ["tasks", "update", "task-1", "--title", "Updated"], "api_error"),
    ("close_task", _ERR, ["tasks", "close", "task-1"], "api_error"),
    ("reopen_task", _ERR, ["tasks", "reopen", "task-1"], "api_error"),
    ("move_task", _ERR, ["tasks", "move", "task-1", "--after", "task-2"], "api_error"),
    ("delete_task", _ERR, ["tasks", "delete", "task-1"], "api_error"),
    # Tags
    ("list_tags", _ERR, ["tags", "list", "--json"], "api_error"),
    ("get_tag", NotFoundError("Not found"), ["tags", "get", "tag-999", "--json"], "not_found"),
    ("create_tag", _ERR, ["tags", "create", "--name", "test"], "api_error"),
    ("update_tag", _ERR, ["tags", "update", "tag-1", "--name", "updated"], "api_error"),
    ("delete_tag", _ERR, ["tags", "delete", "tag-1"], "api_error"),
    # Quick views
    ("list_all_events", _ERR, ["next", "--json"], "api_error"),
    ("list_all_events", _ERR, ["today", "--json"], "api_error"),
]


class TestErrorHandling:
    """Error handling paths output structured JSON errors to stderr."""

    def _assert_structured_error(self, result, error_type: str) -> None:  # type: ignore[no-untyped-def]
        """Assert exit code 1 and structured error JSON on stderr."""
        assert result.exit_code == 1
        err = json.loads(result.output)
        assert err["error"]["type"] == error_type
        assert "message" in err["error"]

    @pytest.mark.parametrize(
        ("patch_method", "exception", "cli_args", "expected_type"),
        _ERROR_CASES,
    )
    def test_error_mapping(
        self,
        runner: CliRunner,
        mock_client,  # type: ignore[no-untyped-def]
        patch_method: str,
        exception: Exception,
        cli_args: list[str],
        expected_type: str,
    ) -> None:
        with patch.object(mock_client, patch_method, side_effect=exception):
            result = runner.invoke(cli, cli_args, catch_exceptions=False)
        self._assert_structured_error(result, expected_type)

    def test_tasks_list_rate_limit(self, runner: CliRunner, mock_client) -> None:  # type: ignore[no-untyped-def]
        with patch.object(mock_client, "list_all_tasks", side_effect=RateLimitError("Rate limit exceeded")):
            result = runner.invoke(cli, ["tasks", "list", "--json"], catch_exceptions=False)
        self._assert_structured_error(result, "rate_limit_error")
        err = json.loads(result.output)
        assert "suggestions" in err["error"]

    def test_error_with_suggestions(self, runner: CliRunner, mock_client) -> None:  # type: ignore[no-untyped-def]
        with patch.object(
            mock_client,
            "list_accounts",
            side_effect=AuthenticationError("Invalid API key"),
        ):
            result = runner.invoke(cli, ["accounts", "--json"], catch_exceptions=False)
        err = json.loads(result.output)
        assert "suggestions" in err["error"]
        assert any("MORGEN_API_KEY" in s for s in err["error"]["suggestions"])
