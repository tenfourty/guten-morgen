"""Tests for projection helpers (event/task compact + structured participants).

Regression for #46: these helpers must live in a module that does NOT require the
optional `mcp` dependency. The CLI uses them for `events get` and `today/this-week/
this-month --compact` and breaks for users who installed `guten-morgen` without the
`[mcp]` extra when they reach into `guten_morgen.mcp_server` for these helpers.
"""

from __future__ import annotations

from pathlib import Path


class TestStructuredParticipants:
    def test_filters_out_resource_kind(self) -> None:
        from guten_morgen.projection import _structured_participants

        participants = {
            "p1": {"name": "Alice", "email": "a@x", "participationStatus": "accepted"},
            "p2": {"name": "Room 42", "email": "room@x", "kind": "resource"},
        }
        result = _structured_participants(participants)
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_marks_account_owner_as_organiser(self) -> None:
        from guten_morgen.projection import _structured_participants

        participants = {
            "owner": {"email": "me@x", "accountOwner": True, "participationStatus": "accepted"},
        }
        result = _structured_participants(participants)
        assert result[0]["is_organiser"] is True

    def test_returns_empty_list_for_none(self) -> None:
        from guten_morgen.projection import _structured_participants

        assert _structured_participants(None) == []


class TestCompactEvent:
    def test_strips_id_and_adds_duration_minutes(self) -> None:
        from guten_morgen.projection import _compact_event

        event = {
            "id": "evt-1",
            "title": "Standup",
            "start": "2026-02-17T09:00:00",
            "duration": "PT1H30M",
            "my_status": "accepted",
            "location_display": "Room 42",
            "participants": {"p1": {"name": "Alice"}, "p2": {"name": "Bob"}},
        }
        result = _compact_event(event)
        assert "id" not in result
        assert result["duration_minutes"] == 90
        assert result["participant_count"] == 2


class TestCompactTask:
    def test_strips_id_and_nulls(self) -> None:
        from guten_morgen.projection import _compact_task

        task = {
            "id": "task-1",
            "title": "Review PR",
            "due": None,
            "source": "morgen",
            "tag_names": ["Right-Now"],
            "list_name": "Inbox",
            "project": None,
        }
        result = _compact_task(task)
        assert "id" not in result
        assert "due" not in result
        assert "project" not in result
        assert result["title"] == "Review PR"
        assert result["list_name"] == "Inbox"


class TestImportLeak:
    """Structural regression for #46.

    `cli.py` must NOT reach into `guten_morgen.mcp_server` for projection helpers, because
    importing `mcp_server` requires the optional `mcp` package. The helpers live in
    `guten_morgen.projection` (no MCP dependency) — both the CLI and the MCP server import
    from there.
    """

    def test_cli_does_not_import_projection_helpers_from_mcp_server(self) -> None:
        cli_src = (Path(__file__).resolve().parent.parent / "src" / "guten_morgen" / "cli.py").read_text()
        for helper in ("_structured_participants", "_compact_event", "_compact_task"):
            forbidden = f"from guten_morgen.mcp_server import {helper}"
            assert forbidden not in cli_src, (
                f"cli.py imports `{helper}` from guten_morgen.mcp_server, which pulls in the "
                f"optional `mcp` dependency at module load. Import it from "
                f"guten_morgen.projection instead."
            )
