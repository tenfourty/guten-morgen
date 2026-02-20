"""MorgenClient — typed httpx wrapper for the Morgen API."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, TypeVar, cast

import httpx

from guten_morgen.cache import (
    TTL_ACCOUNTS,
    TTL_CALENDARS,
    TTL_EVENTS,
    TTL_SINGLE,
    TTL_TAGS,
    TTL_TASK_ACCOUNTS,
    TTL_TASKS,
)
from guten_morgen.errors import (
    AuthenticationError,
    MorgenAPIError,
    NotFoundError,
    RateLimitError,
)
from guten_morgen.models import Account, Calendar, Event, LabelDef, MorgenModel, Space, Tag, Task, TaskListResponse

if TYPE_CHECKING:
    from guten_morgen.config import Settings

T = TypeVar("T", bound=MorgenModel)


def _extract_list(data: Any, key: str, model: type[T]) -> list[T]:
    """Extract and validate a list from Morgen's nested response format."""
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        inner = data.get("data", data)
        if isinstance(inner, dict):
            raw = inner.get(key, [])
        elif isinstance(inner, list):
            raw = inner
        else:
            raw = []
    else:
        raw = []
    return [model.model_validate(item) for item in raw]


def _extract_single(data: Any, key: str, model: type[T]) -> T | None:
    """Extract and validate a single item from Morgen's nested response format.

    Morgen wraps single-item responses as: {"data": {"<key>": {...}}}
    Some endpoints return the item directly. 204 returns None.
    """
    if data is None:
        return None
    if isinstance(data, dict):
        inner = data.get("data", data)
        if isinstance(inner, dict):
            if key in inner:
                return model.model_validate(inner[key])
            return model.model_validate(inner)
        return model.model_validate(data)
    return model.model_validate(data)


class MorgenClient:
    """Sync HTTP client for the Morgen v3 API."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        cache: Any | None = None,
    ) -> None:
        self._cache = cache
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

    def _cache_get(self, key: str) -> Any | None:
        if self._cache is not None:
            return self._cache.get(key)
        return None

    def _cache_set(self, key: str, data: Any, ttl: int) -> None:
        if self._cache is not None:
            self._cache.set(key, data, ttl)

    def _cache_invalidate(self, prefix: str) -> None:
        if self._cache is not None:
            self._cache.invalidate(prefix)

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

    def list_accounts(self) -> list[Account]:
        """List connected calendar accounts."""
        cached = self._cache_get("accounts")
        if cached is not None:
            return [Account.model_validate(a) for a in cast("list[dict[str, Any]]", cached)]
        data = self._request("GET", "/integrations/accounts/list")
        result = _extract_list(data, "accounts", Account)
        self._cache_set("accounts", [a.model_dump() for a in result], TTL_ACCOUNTS)
        return result

    def list_task_accounts(self) -> list[Account]:
        """List accounts with task integrations (Linear, Notion, etc.)."""
        cached = self._cache_get("task_accounts")
        if cached is not None:
            return [Account.model_validate(a) for a in cast("list[dict[str, Any]]", cached)]
        accounts = self.list_accounts()
        result = [a for a in accounts if "tasks" in a.integrationGroups]
        self._cache_set("task_accounts", [a.model_dump() for a in result], TTL_TASK_ACCOUNTS)
        return result

    # ----- Calendars -----

    def list_calendars(self) -> list[Calendar]:
        """List all calendars."""
        cached = self._cache_get("calendars")
        if cached is not None:
            return [Calendar.model_validate(c) for c in cast("list[dict[str, Any]]", cached)]
        data = self._request("GET", "/calendars/list")
        result = _extract_list(data, "calendars", Calendar)
        self._cache_set("calendars", [c.model_dump() for c in result], TTL_CALENDARS)
        return result

    # ----- Events -----

    def list_events(
        self,
        account_id: str,
        calendar_ids: list[str],
        start: str,
        end: str,
    ) -> list[Event]:
        """List events in a date range."""
        raw = f"{account_id}:{','.join(sorted(calendar_ids))}:{start}:{end}"
        key = f"events/{hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:12]}"
        cached = self._cache_get(key)
        if cached is not None:
            return [Event.model_validate(e) for e in cast("list[dict[str, Any]]", cached)]
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
        result = _extract_list(data, "events", Event)
        self._cache_set(key, [e.model_dump(by_alias=True) for e in result], TTL_EVENTS)
        return result

    def list_all_events(
        self,
        start: str,
        end: str,
        *,
        account_keys: list[str] | None = None,
        calendar_names: list[str] | None = None,
        active_only: bool = False,
    ) -> list[Event]:
        """List events across calendar-capable accounts, deduplicating synced copies.

        Fans out list_events() per account, then filters out "(via Morgen)"
        synced copies to avoid duplicates.

        Optional filters:
        - account_keys: "email:provider" strings to match against accounts
        - calendar_names: whitelist of calendar names within matched accounts
        - active_only: skip calendars where isActiveByDefault is not True
        """
        from guten_morgen.groups import match_account

        accounts = self.list_accounts()
        calendars = self.list_calendars()

        # Filter accounts by key if specified
        if account_keys:
            accounts = [a for a in accounts if any(match_account(a.model_dump(), k) for k in account_keys)]

        # Filter calendars: explicit name whitelist takes priority over active_only
        if calendar_names:
            name_set = set(calendar_names)
            calendars = [c for c in calendars if c.name in name_set]
        elif active_only:
            calendars = [c for c in calendars if c.isActiveByDefault is True]

        # Group calendars by accountId
        cals_by_account: dict[str, list[str]] = {}
        for cal in calendars:
            aid = cal.accountId or ""
            cid = cal.id or cal.calendarId or ""
            if aid and cid:
                cals_by_account.setdefault(aid, []).append(cid)

        all_events: list[Event] = []
        for account in accounts:
            if "calendars" not in account.integrationGroups:
                continue
            aid = account.id
            cal_ids = cals_by_account.get(aid, [])
            if not cal_ids:
                continue
            all_events.extend(self.list_events(aid, cal_ids, start, end))

        # Deduplicate: remove "(via Morgen)" synced copies
        return [e for e in all_events if "(via Morgen)" not in (e.title or "")]

    def create_event(self, event_data: dict[str, Any]) -> Event | None:
        """Create a new event."""
        data = self._request("POST", "/events/create", json=event_data)
        self._cache_invalidate("events")
        return _extract_single(data, "event", Event)

    def update_event(self, event_data: dict[str, Any]) -> Event | None:
        """Update an existing event."""
        data = self._request("POST", "/events/update", json=event_data)
        self._cache_invalidate("events")
        return _extract_single(data, "event", Event)

    def delete_event(self, event_data: dict[str, Any]) -> None:
        """Delete an event."""
        self._request("POST", "/events/delete", json=event_data)
        self._cache_invalidate("events")

    # ----- Tasks -----

    def list_all_tasks(
        self,
        *,
        source: str | None = None,
        limit: int = 100,
    ) -> TaskListResponse:
        """List tasks across all connected task sources.

        Returns a TaskListResponse with tasks merged from all sources.

        If source is specified, only fetch from that integration.
        "morgen" fetches native tasks (no accountId param).
        """
        all_tasks_raw: list[dict[str, Any]] = []
        all_label_defs_raw: list[dict[str, Any]] = []
        all_spaces_raw: list[dict[str, Any]] = []

        # Morgen-native tasks — Task model defaults integrationId="morgen"
        if source is None or source == "morgen":
            data = self._request("GET", "/tasks/list", params={"limit": limit})
            # Inline raw-dict extraction (Morgen wraps as {"data": {"tasks": [...]}})
            if isinstance(data, dict):
                inner = data.get("data", data)
                if isinstance(inner, dict):
                    all_tasks_raw.extend(inner.get("tasks", []))
                elif isinstance(inner, list):
                    all_tasks_raw.extend(inner)
            elif isinstance(data, list):
                all_tasks_raw.extend(data)

        # External task sources
        task_accounts = self.list_task_accounts()
        for account in task_accounts:
            integration = account.integrationId or ""
            if source is not None and integration != source:
                continue
            account_id = account.id
            if not account_id:
                continue

            cache_key = f"tasks/{account_id}"
            cached = self._cache_get(cache_key)
            if cached is not None:
                inner = cast("dict[str, Any]", cached)
            else:
                raw = self._request(
                    "GET",
                    "/tasks/list",
                    params={"accountId": account_id, "limit": limit},
                )
                # _request returns resp.json() which is {"data": {...}}
                # Unwrap the data envelope to get the inner dict
                if isinstance(raw, dict):
                    inner = raw.get("data", raw)
                else:
                    inner = {}
                self._cache_set(cache_key, inner, TTL_TASKS)

            all_tasks_raw.extend(inner.get("tasks", []))
            all_label_defs_raw.extend(inner.get("labelDefs", []))
            all_spaces_raw.extend(inner.get("spaces", []))

        return TaskListResponse(
            tasks=[Task.model_validate(t) for t in all_tasks_raw],
            labelDefs=[LabelDef.model_validate(ld) for ld in all_label_defs_raw],
            spaces=[Space.model_validate(s) for s in all_spaces_raw],
        )

    def list_tasks(self, limit: int = 100, updated_after: str | None = None) -> list[Task]:
        """List tasks."""
        cached = self._cache_get("tasks/list")
        if cached is not None:
            return [Task.model_validate(t) for t in cast("list[dict[str, Any]]", cached)]
        params: dict[str, Any] = {"limit": limit}
        if updated_after:
            params["updatedAfter"] = updated_after
        data = self._request("GET", "/tasks/list", params=params)
        result = _extract_list(data, "tasks", Task)
        self._cache_set("tasks/list", [t.model_dump() for t in result], TTL_TASKS)
        return result

    def get_task(self, task_id: str) -> Task:
        """Get a single task."""
        key = f"tasks/{task_id}"
        cached = self._cache_get(key)
        if cached is not None:
            return Task.model_validate(cast("dict[str, Any]", cached))
        data = self._request("GET", "/tasks/", params={"id": task_id})
        result = _extract_single(data, "task", Task)
        if result is None:
            raise NotFoundError(f"Task {task_id} not found")
        self._cache_set(key, result.model_dump(), TTL_SINGLE)
        return result

    def create_task(self, task_data: dict[str, Any]) -> Task | None:
        """Create a new task."""
        data = self._request("POST", "/tasks/create", json=task_data)
        self._cache_invalidate("tasks")
        return _extract_single(data, "task", Task)

    def update_task(self, task_data: dict[str, Any]) -> Task | None:
        """Update a task."""
        data = self._request("POST", "/tasks/update", json=task_data)
        self._cache_invalidate("tasks")
        return _extract_single(data, "task", Task)

    def close_task(self, task_id: str) -> Task | None:
        """Mark a task as completed."""
        data = self._request("POST", "/tasks/close", json={"id": task_id})
        self._cache_invalidate("tasks")
        return _extract_single(data, "task", Task)

    def reopen_task(self, task_id: str) -> Task | None:
        """Reopen a completed task."""
        data = self._request("POST", "/tasks/reopen", json={"id": task_id})
        self._cache_invalidate("tasks")
        return _extract_single(data, "task", Task)

    def move_task(self, task_id: str, after: str | None = None, parent: str | None = None) -> Task | None:
        """Reorder or nest a task."""
        payload: dict[str, Any] = {"id": task_id}
        if after is not None:
            payload["after"] = after
        if parent is not None:
            payload["parent"] = parent
        data = self._request("POST", "/tasks/move", json=payload)
        self._cache_invalidate("tasks")
        return _extract_single(data, "task", Task)

    def delete_task(self, task_id: str) -> None:
        """Delete a task."""
        self._request("POST", "/tasks/delete", json={"id": task_id})
        self._cache_invalidate("tasks")

    def schedule_task(
        self,
        task_id: str,
        start: str,
        calendar_id: str,
        account_id: str,
        *,
        duration_minutes: int | None = None,
        timezone: str | None = None,
    ) -> Event | None:
        """Schedule a task as a linked calendar event.

        Fetches the task to derive title and duration, then creates an event
        with morgen.so:metadata.taskId linking it back to the task.
        """
        task = self.get_task(task_id)
        title = task.title or "Untitled task"

        # Duration: explicit override > task's estimatedDuration > 30min default
        if duration_minutes is not None:
            duration = f"PT{duration_minutes}M"
        else:
            duration = task.estimatedDuration or "PT30M"

        # Default to system timezone if not specified (API requires it for timed events)
        if not timezone:
            from guten_morgen.time_utils import get_local_timezone

            timezone = get_local_timezone()

        event_data: dict[str, Any] = {
            "title": title,
            "start": start,
            "duration": duration,
            "calendarId": calendar_id,
            "accountId": account_id,
            "showWithoutTime": False,
            "timeZone": timezone,
            "morgen.so:metadata": {"taskId": task_id},
        }

        return self.create_event(event_data)

    # ----- Tags -----

    def list_tags(self) -> list[Tag]:
        """List all tags."""
        cached = self._cache_get("tags")
        if cached is not None:
            return [Tag.model_validate(t) for t in cast("list[dict[str, Any]]", cached)]
        data = self._request("GET", "/tags/list")
        result = _extract_list(data, "tags", Tag)
        self._cache_set("tags", [t.model_dump() for t in result], TTL_TAGS)
        return result

    def get_tag(self, tag_id: str) -> Tag:
        """Get a single tag."""
        key = f"tags/{tag_id}"
        cached = self._cache_get(key)
        if cached is not None:
            return Tag.model_validate(cast("dict[str, Any]", cached))
        data = self._request("GET", "/tags/", params={"id": tag_id})
        result = _extract_single(data, "tag", Tag)
        if result is None:
            raise NotFoundError(f"Tag {tag_id} not found")
        self._cache_set(key, result.model_dump(), TTL_SINGLE)
        return result

    def create_tag(self, tag_data: dict[str, Any]) -> Tag | None:
        """Create a tag."""
        data = self._request("POST", "/tags/create", json=tag_data)
        self._cache_invalidate("tags")
        return _extract_single(data, "tag", Tag)

    def update_tag(self, tag_data: dict[str, Any]) -> Tag | None:
        """Update a tag."""
        data = self._request("POST", "/tags/update", json=tag_data)
        self._cache_invalidate("tags")
        return _extract_single(data, "tag", Tag)

    def delete_tag(self, tag_id: str) -> None:
        """Delete a tag."""
        self._request("POST", "/tags/delete", json={"id": tag_id})
        self._cache_invalidate("tags")
