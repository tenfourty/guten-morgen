"""Calendar group configuration and filter resolution."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]

from guten_morgen.config import find_config
from guten_morgen.errors import GroupNotFoundError


@dataclass
class GroupConfig:
    """A named calendar group."""

    accounts: list[str]
    calendars: list[str] | None = None


@dataclass
class MorgenConfig:
    """Top-level morgen configuration."""

    default_group: str | None = None
    active_only: bool = False
    groups: dict[str, GroupConfig] = field(default_factory=dict)
    task_calendar: str | None = None
    task_calendar_account: str | None = None


@dataclass
class CalendarFilter:
    """Resolved filter to apply when listing events."""

    account_keys: list[str] | None = None  # None = all accounts
    calendar_names: list[str] | None = None  # None = all calendars
    active_only: bool = False


def load_morgen_config(path: Path | None = None) -> MorgenConfig:
    """Load configuration from TOML file.

    Uses find_config() for XDG-compliant discovery when no path given.
    Returns no-op defaults if no config file found.
    """
    if path is None:
        found = find_config()
        if found is None:
            return MorgenConfig()
        path = found

    if not path.exists():
        return MorgenConfig()

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    groups: dict[str, GroupConfig] = {}
    for name, gdata in raw.get("groups", {}).items():
        groups[name] = GroupConfig(
            accounts=gdata.get("accounts", []),
            calendars=gdata.get("calendars") or None,
        )

    return MorgenConfig(
        default_group=raw.get("default_group"),
        active_only=raw.get("active_only", False),
        groups=groups,
        task_calendar=raw.get("task_calendar"),
        task_calendar_account=raw.get("task_calendar_account"),
    )


def resolve_filter(
    config: MorgenConfig,
    group: str | None = None,
    all_calendars: bool = False,
) -> CalendarFilter:
    """Resolve CLI options into a CalendarFilter."""
    active_only = config.active_only and not all_calendars

    # --group all: no account/calendar filtering
    if group == "all":
        return CalendarFilter(active_only=active_only)

    # Explicit group name or default
    group_name = group or config.default_group
    if group_name is None:
        return CalendarFilter(active_only=active_only)

    if group_name not in config.groups:
        available = sorted(config.groups.keys())
        suggestions = (
            [f"Available groups: {', '.join(available)}"] if available else ["No groups configured — run `gm init`"]
        )
        raise GroupNotFoundError(f"Unknown group '{group_name}'", suggestions=suggestions)

    gc = config.groups[group_name]
    return CalendarFilter(
        account_keys=gc.accounts,
        calendar_names=gc.calendars,
        active_only=active_only,
    )


def match_account(account: dict[str, Any], key: str) -> bool:
    """Check if an account matches an account key.

    Key format: "email:provider" or just "email".
    Matches against preferredEmail, emails list, and integrationId.
    Google accounts often have preferredEmail=null, so we also check
    the emails array.
    """
    parts = key.split(":", 1)
    email = parts[0]
    provider = parts[1] if len(parts) > 1 else None

    # Check provider first (cheap)
    if provider is not None and account.get("integrationId") != provider:
        return False

    # Check email: preferredEmail or emails list
    preferred = account.get("preferredEmail")
    if preferred == email:
        return True
    emails_list: list[str] = account.get("emails", [])
    return email in emails_list
