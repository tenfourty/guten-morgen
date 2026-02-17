"""Calendar group configuration and filter resolution."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # type: ignore[import-not-found]

from morgen.errors import GroupNotFoundError

# Project root: same as config.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


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


@dataclass
class CalendarFilter:
    """Resolved filter to apply when listing events."""

    account_keys: list[str] | None = None  # None = all accounts
    calendar_names: list[str] | None = None  # None = all calendars
    active_only: bool = False


def load_morgen_config(path: Path | None = None) -> MorgenConfig:
    """Load configuration from TOML file.

    Falls back to MORGEN_CONFIG env var, then .config.toml in project root.
    Returns no-op defaults if file is missing.
    """
    if path is None:
        env_path = os.environ.get("MORGEN_CONFIG")
        if env_path:
            path = Path(env_path)
        else:
            path = _PROJECT_ROOT / ".config.toml"

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
            [f"Available groups: {', '.join(available)}"] if available else ["No groups configured in .config.toml"]
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
    Matches against preferredEmail and integrationId.
    """
    parts = key.split(":", 1)
    email = parts[0]
    provider = parts[1] if len(parts) > 1 else None

    if account.get("preferredEmail") != email:
        return False
    if provider is not None and account.get("integrationId") != provider:
        return False
    return True
