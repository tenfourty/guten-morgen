"""TypedDict definitions for Morgen API objects."""

from __future__ import annotations

from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict


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


class Event(TypedDict, total=False):
    """Calendar event."""

    id: str
    title: str
    description: str
    start: str
    end: str
    duration: str
    calendarId: str
    accountId: str
    participants: dict[str, Any]
    locations: dict[str, Any]
    showAs: str


class Task(TypedDict, total=False):
    """Task item."""

    id: str
    title: str
    description: str
    status: str
    priority: int
    due: str
    createdAt: str
    updatedAt: str
    completedAt: str
    parentId: str
    tags: list[str]


class Tag(MorgenModel):
    """Tag for tasks."""

    id: str
    name: str
    color: str | None = None
