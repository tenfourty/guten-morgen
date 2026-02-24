"""Exception hierarchy and structured error output."""

from __future__ import annotations

import json
import sys


class MorgenError(Exception):
    """Base exception for all Morgen CLI errors."""

    error_type: str = "morgen_error"
    suggestions: list[str] = []

    def __init__(self, message: str, suggestions: list[str] | None = None) -> None:
        super().__init__(message)
        if suggestions is not None:
            self.suggestions = suggestions


class AuthenticationError(MorgenError):
    """Invalid or missing API key."""

    error_type = "authentication_error"
    suggestions = [
        "Run `gm init` to create a config file",
        "Or set MORGEN_API_KEY in your environment",
        "Verify the key at https://platform.morgen.so/",
    ]


class RateLimitError(MorgenError):
    """API rate limit exceeded."""

    error_type = "rate_limit_error"
    suggestions = [
        "Wait for the Retry-After period before retrying",
        "Reduce request frequency",
        "Install Morgen desktop app for 5x higher rate limits (bearer token auth)",
    ]


class NotFoundError(MorgenError):
    """Resource not found."""

    error_type = "not_found"


class MorgenAPIError(MorgenError):
    """Generic API error."""

    error_type = "api_error"


class ConfigError(MorgenError):
    """Configuration error (missing env vars, etc.)."""

    error_type = "config_error"
    suggestions = [
        "Run `gm init` to create a config file",
        "Or set MORGEN_API_KEY in your environment",
    ]


class GroupNotFoundError(MorgenError):
    """Unknown calendar group name."""

    error_type = "group_not_found"


def output_error(error_type: str, message: str, suggestions: list[str] | None = None, exit_code: int = 1) -> None:
    """Write a structured error to stderr and exit."""
    err: dict[str, dict[str, str | list[str]]] = {"error": {"type": error_type, "message": message}}
    if suggestions:
        err["error"]["suggestions"] = suggestions
    print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
    sys.exit(exit_code)
