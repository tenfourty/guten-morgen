"""MorgenClient — typed httpx wrapper for the Morgen API."""

from __future__ import annotations

from typing import Any

import httpx

from morgen.config import Settings
from morgen.errors import (
    AuthenticationError,
    MorgenAPIError,
    NotFoundError,
    RateLimitError,
)


def _extract_list(data: Any, key: str) -> list[dict[str, Any]]:
    """Extract a list from Morgen's nested response format.

    Morgen wraps list responses as: {"data": {"<key>": [...]}}
    Some endpoints return a flat list directly.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        inner = data.get("data", data)
        if isinstance(inner, dict):
            result: list[dict[str, Any]] = inner.get(key, [])
            return result
        if isinstance(inner, list):
            return inner
    return []


class MorgenClient:
    """Sync HTTP client for the Morgen v3 API."""

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self._settings = settings
        kwargs: dict[str, Any] = {
            "base_url": settings.base_url,
            "headers": {"Authorization": f"ApiKey {settings.api_key}"},
            "timeout": settings.timeout,
        }
        if transport is not None:
            kwargs["transport"] = transport
        self._http = httpx.Client(**kwargs)

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an API request with error mapping."""
        resp = self._http.request(method, path, **kwargs)

        if resp.status_code == 401:
            raise AuthenticationError("Invalid or missing API key")
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "unknown")
            raise RateLimitError(
                f"Rate limit exceeded. Retry after {retry_after}s",
                suggestions=[
                    f"Wait {retry_after} seconds before retrying",
                    "Reduce request frequency (100 pts / 15 min)",
                ],
            )
        if resp.status_code == 404:
            raise NotFoundError(f"Resource not found: {path}")
        if resp.status_code >= 400:
            body = resp.text
            raise MorgenAPIError(f"API error {resp.status_code}: {body}")

        if resp.status_code == 204:
            return None

        return resp.json()

    # ----- Accounts -----

    def list_accounts(self) -> list[dict[str, Any]]:
        """List connected calendar accounts."""
        data = self._request("GET", "/integrations/accounts/list")
        return _extract_list(data, "accounts")

    # ----- Calendars -----

    def list_calendars(self) -> list[dict[str, Any]]:
        """List all calendars."""
        data = self._request("GET", "/calendars/list")
        return _extract_list(data, "calendars")

    # ----- Events -----

    def list_events(
        self,
        account_id: str,
        calendar_ids: list[str],
        start: str,
        end: str,
    ) -> list[dict[str, Any]]:
        """List events in a date range."""
        data = self._request(
            "GET",
            "/events/list",
            params={
                "accountId": account_id,
                "calendarIds": ",".join(calendar_ids),
                "start": start,
                "end": end,
            },
        )
        return _extract_list(data, "events")

    def create_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new event."""
        result: dict[str, Any] = self._request("POST", "/events/create", json=event_data)
        return result

    def update_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing event."""
        result: dict[str, Any] = self._request("POST", "/events/update", json=event_data)
        return result

    def delete_event(self, event_data: dict[str, Any]) -> None:
        """Delete an event."""
        self._request("POST", "/events/delete", json=event_data)

    # ----- Tasks -----

    def list_tasks(self, limit: int = 100, updated_after: str | None = None) -> list[dict[str, Any]]:
        """List tasks."""
        params: dict[str, Any] = {"limit": limit}
        if updated_after:
            params["updatedAfter"] = updated_after
        data = self._request("GET", "/tasks/list", params=params)
        return _extract_list(data, "tasks")

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Get a single task."""
        result: dict[str, Any] = self._request("GET", "/tasks/", params={"id": task_id})
        return result

    def create_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new task."""
        result: dict[str, Any] = self._request("POST", "/tasks/create", json=task_data)
        return result

    def update_task(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """Update a task."""
        result: dict[str, Any] = self._request("POST", "/tasks/update", json=task_data)
        return result

    def close_task(self, task_id: str) -> dict[str, Any]:
        """Mark a task as completed."""
        result: dict[str, Any] = self._request("POST", "/tasks/close", json={"id": task_id})
        return result

    def reopen_task(self, task_id: str) -> dict[str, Any]:
        """Reopen a completed task."""
        result: dict[str, Any] = self._request("POST", "/tasks/reopen", json={"id": task_id})
        return result

    def move_task(self, task_id: str, after: str | None = None, parent: str | None = None) -> dict[str, Any]:
        """Reorder or nest a task."""
        payload: dict[str, Any] = {"id": task_id}
        if after is not None:
            payload["after"] = after
        if parent is not None:
            payload["parent"] = parent
        result: dict[str, Any] = self._request("POST", "/tasks/move", json=payload)
        return result

    def delete_task(self, task_id: str) -> None:
        """Delete a task."""
        self._request("POST", "/tasks/delete", json={"id": task_id})

    # ----- Tags -----

    def list_tags(self) -> list[dict[str, Any]]:
        """List all tags."""
        data = self._request("GET", "/tags/list")
        return _extract_list(data, "tags")

    def get_tag(self, tag_id: str) -> dict[str, Any]:
        """Get a single tag."""
        result: dict[str, Any] = self._request("GET", "/tags/", params={"id": tag_id})
        return result

    def create_tag(self, tag_data: dict[str, Any]) -> dict[str, Any]:
        """Create a tag."""
        result: dict[str, Any] = self._request("POST", "/tags/create", json=tag_data)
        return result

    def update_tag(self, tag_data: dict[str, Any]) -> dict[str, Any]:
        """Update a tag."""
        result: dict[str, Any] = self._request("POST", "/tags/update", json=tag_data)
        return result

    def delete_tag(self, tag_id: str) -> None:
        """Delete a tag."""
        self._request("POST", "/tags/delete", json={"id": tag_id})
