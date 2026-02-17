"""Tests for the output formatting pipeline."""

from __future__ import annotations

import json

import pytest

from morgen.errors import output_error
from morgen.output import (
    enrich_events,
    enrich_tasks,
    format_csv_str,
    format_json,
    format_jsonl,
    format_locations,
    format_participants,
    format_table,
    render,
    select_fields,
)

SAMPLE_ROWS = [
    {"id": "1", "title": "Meeting", "start": "09:00"},
    {"id": "2", "title": "Lunch", "start": "12:00"},
]


class TestFormatJson:
    def test_basic(self) -> None:
        result = format_json(SAMPLE_ROWS)
        parsed = json.loads(result)
        assert len(parsed) == 2
        assert parsed[0]["title"] == "Meeting"

    def test_indent(self) -> None:
        result = format_json({"a": 1}, indent=4)
        assert "    " in result


class TestFormatJsonl:
    def test_basic(self) -> None:
        result = format_jsonl(SAMPLE_ROWS)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["title"] == "Meeting"


class TestFormatCsv:
    def test_basic(self) -> None:
        result = format_csv_str(SAMPLE_ROWS)
        lines = result.strip().split("\n")
        assert "id" in lines[0]
        assert "Meeting" in lines[1]

    def test_empty(self) -> None:
        assert format_csv_str([]) == ""

    def test_columns(self) -> None:
        result = format_csv_str(SAMPLE_ROWS, columns=["title"])
        assert "id" not in result.split("\n")[0]
        assert "title" in result.split("\n")[0]


class TestFormatTable:
    def test_basic(self) -> None:
        result = format_table(SAMPLE_ROWS)
        assert "Meeting" in result
        assert "Lunch" in result

    def test_empty(self) -> None:
        assert format_table([]) == "No results."

    def test_long_values_not_truncated_to_unusable(self) -> None:
        """Table should handle long values without making other columns unreadable."""
        rows = [
            {"id": "a" * 200, "title": "Important Meeting", "start": "09:00"},
        ]
        result = format_table(rows, columns=["id", "title", "start"])
        # Title should still be readable in the output
        assert "Important Meeting" in result

    def test_id_column_max_width(self) -> None:
        """ID columns should be truncated in table format to save space."""
        rows = [
            {"id": "a" * 200, "title": "Test"},
        ]
        result = format_table(rows, columns=["id", "title"])
        # The full 200-char ID should not appear
        assert "a" * 200 not in result
        # A short hash should appear instead
        assert len(result) < 250  # table itself is compact


class TestSelectFields:
    def test_list(self) -> None:
        result = select_fields(SAMPLE_ROWS, ["id", "title"])
        assert all("start" not in r for r in result)
        assert all("id" in r for r in result)

    def test_dict(self) -> None:
        result = select_fields({"id": "1", "title": "X", "extra": "Y"}, ["id", "title"])
        assert "extra" not in result

    def test_dict_with_results(self) -> None:
        data = {"total": 2, "results": SAMPLE_ROWS}
        result = select_fields(data, ["id"])
        assert result["total"] == 2
        assert all("title" not in r for r in result["results"])


class TestRender:
    def test_json(self) -> None:
        result = render(SAMPLE_ROWS, fmt="json")
        assert json.loads(result)[0]["title"] == "Meeting"

    def test_jsonl(self) -> None:
        result = render(SAMPLE_ROWS, fmt="jsonl")
        assert len(result.strip().split("\n")) == 2

    def test_csv(self) -> None:
        result = render(SAMPLE_ROWS, fmt="csv")
        assert "Meeting" in result

    def test_table(self) -> None:
        result = render(SAMPLE_ROWS, fmt="table")
        assert "Meeting" in result

    def test_fields(self) -> None:
        result = render(SAMPLE_ROWS, fmt="json", fields=["title"])
        parsed = json.loads(result)
        assert "id" not in parsed[0]

    def test_jq(self) -> None:
        result = render(SAMPLE_ROWS, fmt="json", jq_expr=".[0].title")
        assert json.loads(result) == "Meeting"


class TestTruncateIds:
    def test_truncate_ids(self) -> None:
        from morgen.output import truncate_ids

        data = [{"id": "a" * 200, "title": "Test"}]
        result = truncate_ids(data)
        assert len(result[0]["id"]) == 12
        assert result[0]["title"] == "Test"

    def test_truncate_ids_short_id(self) -> None:
        from morgen.output import truncate_ids

        data = [{"id": "short", "title": "Test"}]
        result = truncate_ids(data)
        assert result[0]["id"] == "short"

    def test_truncate_ids_nested_dict(self) -> None:
        from morgen.output import truncate_ids

        data = {"id": "x" * 50, "name": "foo"}
        result = truncate_ids(data)
        assert len(result["id"]) == 12

    def test_truncate_preserves_non_id(self) -> None:
        from morgen.output import truncate_ids

        data = [{"id": "abc123", "description": "a" * 200}]
        result = truncate_ids(data)
        assert len(result[0]["description"]) == 200

    def test_truncate_recurses_into_nested_lists(self) -> None:
        """Handles {"events": [{"id": "long..."}]} structure."""
        from morgen.output import truncate_ids

        data = {"events": [{"id": "x" * 200, "title": "Test"}], "count": 1}
        result = truncate_ids(data)
        assert len(result["events"][0]["id"]) == 12
        assert result["count"] == 1

    def test_different_ids_produce_different_hashes(self) -> None:
        """Different long IDs produce distinct short IDs."""
        from morgen.output import truncate_ids

        data = [
            {"id": "SHARED_PREFIX_UNIQUE_A"},
            {"id": "SHARED_PREFIX_UNIQUE_B"},
        ]
        result = truncate_ids(data, length=12)
        assert result[0]["id"] != result[1]["id"]
        assert len(result[0]["id"]) == 12


class TestFormatParticipants:
    def test_basic(self) -> None:
        participants = {
            "p1": {"name": "Alice", "email": "alice@example.com", "kind": "individual"},
            "p2": {"name": "Bob", "email": "bob@example.com", "kind": "individual"},
        }
        assert format_participants(participants) == "Alice, Bob"

    def test_filters_resources(self) -> None:
        participants = {
            "p1": {"name": "Alice", "kind": "individual"},
            "p2": {"name": "Room 42", "kind": "resource"},
        }
        assert format_participants(participants) == "Alice"

    def test_email_fallback(self) -> None:
        participants = {
            "p1": {"email": "alice@example.com", "kind": "individual"},
        }
        assert format_participants(participants) == "alice@example.com"

    def test_empty(self) -> None:
        assert format_participants(None) == ""
        assert format_participants({}) == ""


class TestFormatLocations:
    def test_basic(self) -> None:
        locations = {
            "loc1": {"name": "Room A"},
            "loc2": {"name": "meet.google.com/xyz"},
        }
        assert format_locations(locations) == "Room A, meet.google.com/xyz"

    def test_empty(self) -> None:
        assert format_locations(None) == ""
        assert format_locations({}) == ""


class TestEnrichEvents:
    def test_adds_display_fields(self) -> None:
        events = [
            {
                "id": "e1",
                "title": "Standup",
                "participants": {
                    "p1": {"name": "Alice", "kind": "individual"},
                },
                "locations": {
                    "loc1": {"name": "Room A"},
                },
            },
        ]
        result = enrich_events(events)
        assert result[0]["participants_display"] == "Alice"
        assert result[0]["location_display"] == "Room A"

    def test_no_mutation(self) -> None:
        events = [{"id": "e1", "title": "Test"}]
        result = enrich_events(events)
        assert "participants_display" not in events[0]
        assert "participants_display" in result[0]

    def test_empty_participants_and_locations(self) -> None:
        events = [{"id": "e1", "title": "Test"}]
        result = enrich_events(events)
        assert result[0]["participants_display"] == ""
        assert result[0]["location_display"] == ""


class TestEnrichTasks:
    def test_morgen_native_task(self) -> None:
        tasks = [{"id": "t1", "title": "Review PR", "integrationId": "morgen", "progress": "needs-action"}]
        result = enrich_tasks(tasks)
        assert result[0]["source"] == "morgen"
        assert result[0]["source_id"] is None
        assert result[0]["source_url"] is None
        assert result[0]["source_status"] is None

    def test_linear_task(self) -> None:
        tasks = [
            {
                "id": "lt1",
                "title": "Budget planning",
                "integrationId": "linear",
                "progress": "needs-action",
                "links": {"original": {"href": "https://linear.app/co/issue/ENG-1740/budget"}},
                "labels": [
                    {"id": "identifier", "value": "ENG-1740"},
                    {"id": "state", "value": "state-1"},
                ],
            }
        ]
        label_defs = [
            {
                "id": "state",
                "label": "Status",
                "type": "enum",
                "values": [{"value": "state-1", "label": "In Progress"}],
            },
        ]
        result = enrich_tasks(tasks, label_defs=label_defs)
        assert result[0]["source"] == "linear"
        assert result[0]["source_id"] == "ENG-1740"
        assert result[0]["source_url"] == "https://linear.app/co/issue/ENG-1740/budget"
        assert result[0]["source_status"] == "In Progress"

    def test_notion_task(self) -> None:
        tasks = [
            {
                "id": "nt1",
                "title": "Update Ladder",
                "integrationId": "notion",
                "progress": "needs-action",
                "links": {"original": {"href": "https://www.notion.so/abc123"}},
                "labels": [
                    {"id": "notion%3A%2F%2Fprojects%2Fstatus_property", "value": "in-progress"},
                ],
            }
        ]
        label_defs = [
            {
                "id": "notion%3A%2F%2Fprojects%2Fstatus_property",
                "label": "Status",
                "type": "enum",
                "values": [{"value": "in-progress", "label": "In Progress"}],
            },
        ]
        result = enrich_tasks(tasks, label_defs=label_defs)
        assert result[0]["source"] == "notion"
        assert result[0]["source_url"] == "https://www.notion.so/abc123"
        assert result[0]["source_status"] == "In Progress"

    def test_no_labels_graceful(self) -> None:
        tasks = [{"id": "t1", "title": "Bare task", "progress": "needs-action"}]
        result = enrich_tasks(tasks)
        assert result[0]["source"] == "morgen"  # default when integrationId missing
        assert result[0]["source_id"] is None


class TestOutputError:
    def test_structured_output(self) -> None:
        with pytest.raises(SystemExit) as exc_info:
            output_error("test_error", "something went wrong", ["try this"])
        assert exc_info.value.code == 1
