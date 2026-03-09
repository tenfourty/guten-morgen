"""TypedDict definitions for Morgen API objects."""

from __future__ import annotations

import base64
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


class MorgenModel(BaseModel):
    """Base model for all Morgen API objects.

    - extra="ignore": resilient to API additions (new fields don't break us)
    - populate_by_name=True: allows both alias and field name for construction
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Account(MorgenModel):
    """Connected calendar account."""

    id: str
    name: str | None = None
    providerUserDisplayName: str | None = None
    preferredEmail: str | None = None
    integrationId: str | None = None
    integrationGroups: list[str] = []
    providerId: str | None = None
    providerAccountId: str | None = None
    email: str | None = None


class Calendar(MorgenModel):
    """Calendar within an account."""

    id: str
    calendarId: str | None = None
    accountId: str | None = None
    name: str | None = None
    color: str | None = None
    writable: bool | None = None
    isActiveByDefault: bool | None = None
    myRights: Any = None  # Can be dict or string depending on provider


class Event(MorgenModel):
    """Calendar event."""

    id: str
    title: str | None = None
    description: str | None = None
    start: str | None = None
    end: str | None = None
    duration: str | None = None
    calendarId: str | None = None
    accountId: str | None = None
    participants: dict[str, Any] | None = None
    locations: dict[str, Any] | None = None
    showAs: str | None = None
    showWithoutTime: bool | None = None
    privacy: str | None = None
    freeBusyStatus: str | None = None
    timeZone: str | None = None
    morgen_metadata: dict[str, Any] | None = Field(None, alias="morgen.so:metadata")
    request_virtual_room: str | None = Field(None, alias="morgen.so:requestVirtualRoom")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def calendar_uid(self) -> str | None:
        """Extract the raw provider event ID from the Morgen compound ID.

        Morgen IDs are base64-encoded JSON arrays: ["email", "gcal_event_id", "account_id"].
        Returns the second element (provider event ID), or None if the ID isn't a compound ID.
        """
        try:
            padded = self.id + "=" * (-len(self.id) % 4)
            decoded = base64.b64decode(padded).decode()
            parts = json.loads(decoded)
            if isinstance(parts, list) and len(parts) >= 2:
                return str(parts[1])
        except Exception:  # noqa: BLE001  # nosec B110
            pass
        return None


class LabelDef(MorgenModel):
    """Label definition from task list response (external integrations)."""

    id: str
    label: str | None = None
    type: str | None = None
    values: list[dict[str, Any]] = []


class Space(MorgenModel):
    """Space/project from task list response (external integrations)."""

    id: str
    name: str | None = None


class Task(MorgenModel):
    """Task item."""

    id: str
    title: str = ""
    description: str | None = None
    progress: str | None = None
    status: str | None = None
    priority: int | None = None
    due: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None
    completedAt: str | None = None
    parentId: str | None = None
    tags: list[str] = []
    taskListId: str | None = None
    estimatedDuration: str | None = None
    integrationId: str = "morgen"
    accountId: str | None = None
    labels: list[dict[str, Any]] = []
    links: dict[str, Any] = {}
    occurrenceStart: str | None = None
    position: int | None = None
    earliestStart: str | None = None
    descriptionContentType: str | None = None


class TaskListResponse(MorgenModel):
    """Compound response from list_all_tasks."""

    tasks: list[Task] = []
    labelDefs: list[LabelDef] = []
    spaces: list[Space] = []


class TaskList(MorgenModel):
    """Task list (project/folder for tasks)."""

    id: str
    name: str
    color: str | None = None
    role: str | None = None
    serviceName: str | None = None
    position: int | None = None
    created: str | None = None
    updated: str | None = None


class Tag(MorgenModel):
    """Tag for tasks."""

    id: str
    name: str
    color: str | None = None
