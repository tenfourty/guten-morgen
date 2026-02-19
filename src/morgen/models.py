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


class Account(TypedDict, total=False):
    """Connected calendar account."""

    accountId: str
    providerId: str
    providerAccountId: str
    name: str
    email: str
    preferredEmail: str
    integrationId: str
    integrationGroups: list[str]


class Calendar(TypedDict, total=False):
    """Calendar within an account."""

    calendarId: str
    accountId: str
    name: str
    color: str
    writable: bool
    isActiveByDefault: bool


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


class Tag(TypedDict, total=False):
    """Tag for tasks."""

    id: str
    name: str
    color: str
