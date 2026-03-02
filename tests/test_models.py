"""Tests for Pydantic models."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from guten_morgen.models import Account, Calendar, Event, LabelDef, Space, Tag, Task, TaskList, TaskListResponse

FIXTURES = Path(__file__).parent / "fixtures"


class TestTagModel:
    def test_valid_tag(self) -> None:
        tag = Tag(id="tag-1", name="urgent", color="#ff0000")
        assert tag.id == "tag-1"
        assert tag.name == "urgent"
        assert tag.color == "#ff0000"

    def test_optional_color(self) -> None:
        tag = Tag(id="tag-1", name="urgent")
        assert tag.color is None

    def test_extra_fields_ignored(self) -> None:
        tag = Tag(id="tag-1", name="urgent", unknown_field="whatever")
        assert not hasattr(tag, "unknown_field")

    def test_model_dump_roundtrip(self) -> None:
        tag = Tag(id="tag-1", name="urgent", color="#ff0000")
        d = tag.model_dump()
        assert d == {"id": "tag-1", "name": "urgent", "color": "#ff0000"}

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            Tag(id="tag-1")  # missing name


class TestAccountModel:
    def test_valid_account(self) -> None:
        acc = Account(id="acc-1", name="Work", integrationGroups=["calendars"])
        assert acc.id == "acc-1"
        assert acc.integrationGroups == ["calendars"]

    def test_defaults(self) -> None:
        acc = Account(id="acc-1")
        assert acc.integrationGroups == []
        assert acc.name is None

    def test_extra_ignored(self) -> None:
        acc = Account(id="acc-1", someFutureField="x")
        assert not hasattr(acc, "someFutureField")

    def test_model_dump_roundtrip(self) -> None:
        acc = Account(id="acc-1", name="Work", integrationGroups=["calendars"])
        d = acc.model_dump()
        assert d["id"] == "acc-1"
        assert d["integrationGroups"] == ["calendars"]
        acc2 = Account.model_validate(d)
        assert acc2.id == acc.id

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            Account()  # missing id


class TestCalendarModel:
    def test_valid_calendar(self) -> None:
        cal = Calendar(id="cal-1", accountId="acc-1", name="Work")
        assert cal.name == "Work"

    def test_myRights_can_be_dict_or_string(self) -> None:
        cal1 = Calendar(id="c1", myRights={"mayWriteAll": True})
        cal2 = Calendar(id="c2", myRights="rw")
        assert cal1.myRights == {"mayWriteAll": True}
        assert cal2.myRights == "rw"

    def test_defaults(self) -> None:
        cal = Calendar(id="cal-1")
        assert cal.accountId is None
        assert cal.name is None
        assert cal.myRights is None

    def test_extra_ignored(self) -> None:
        cal = Calendar(id="cal-1", unknownField="x")
        assert not hasattr(cal, "unknownField")

    def test_model_dump_roundtrip(self) -> None:
        cal = Calendar(id="cal-1", accountId="acc-1", name="Work", myRights="rw")
        d = cal.model_dump()
        cal2 = Calendar.model_validate(d)
        assert cal2.id == cal.id
        assert cal2.myRights == "rw"

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            Calendar()  # missing id


class TestEventModel:
    def test_valid_event(self) -> None:
        event = Event(id="evt-1", title="Standup", start="2026-02-17T09:00:00")
        assert event.title == "Standup"

    def test_morgen_metadata_alias(self) -> None:
        event = Event.model_validate(
            {
                "id": "evt-1",
                "title": "Frame",
                "morgen.so:metadata": {"frameFilterMql": "{}"},
            }
        )
        assert event.morgen_metadata is not None
        assert "frameFilterMql" in event.morgen_metadata

    def test_model_dump_by_alias_preserves_metadata_key(self) -> None:
        event = Event.model_validate(
            {
                "id": "evt-1",
                "morgen.so:metadata": {"frameFilterMql": "{}"},
            }
        )
        d = event.model_dump(by_alias=True)
        assert "morgen.so:metadata" in d

    def test_participants_and_locations(self) -> None:
        event = Event(
            id="evt-1",
            participants={"p1": {"name": "Alice"}},
            locations={"loc1": {"name": "Room 42"}},
        )
        assert "p1" in (event.participants or {})

    def test_extra_fields_ignored(self) -> None:
        event = Event(id="evt-1", unknownField="x")
        assert not hasattr(event, "unknownField")

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            Event()  # missing id

    def test_model_dump_roundtrip(self) -> None:
        event = Event.model_validate(
            {
                "id": "evt-1",
                "title": "Test",
                "morgen.so:metadata": {"taskId": "task-1"},
            }
        )
        d = event.model_dump(by_alias=True)
        event2 = Event.model_validate(d)
        assert event2.morgen_metadata == {"taskId": "task-1"}

    def test_populate_by_name(self) -> None:
        """Both Python name and alias work for construction."""
        event = Event(id="evt-1", morgen_metadata={"key": "val"})
        assert event.morgen_metadata == {"key": "val"}
        d = event.model_dump(by_alias=True)
        assert "morgen.so:metadata" in d


class TestEventCalendarUid:
    """Tests for Event.calendar_uid computed field."""

    def _make_compound_id(self, email: str, gcal_id: str, account_id: str) -> str:
        """Build a base64 Morgen compound ID."""
        payload = json.dumps([email, gcal_id, account_id])
        return base64.b64encode(payload.encode()).decode()

    def test_extracts_gcal_id(self) -> None:
        """calendar_uid extracts the second element from the compound ID."""
        compound = self._make_compound_id("user@example.com", "abc123xyz", "acc-1")
        event = Event(id=compound)
        assert event.calendar_uid == "abc123xyz"

    def test_non_base64_id_returns_none(self) -> None:
        """Plain string IDs (not base64-encoded JSON arrays) return None."""
        event = Event(id="evt-1")
        assert event.calendar_uid is None

    def test_base64_non_json_returns_none(self) -> None:
        """Base64 content that isn't a JSON array returns None."""
        encoded = base64.b64encode(b"not json").decode()
        event = Event(id=encoded)
        assert event.calendar_uid is None

    def test_base64_short_array_returns_none(self) -> None:
        """Base64 JSON array with fewer than 2 elements returns None."""
        encoded = base64.b64encode(json.dumps(["only-one"]).encode()).decode()
        event = Event(id=encoded)
        assert event.calendar_uid is None

    def test_included_in_model_dump(self) -> None:
        """calendar_uid appears in model_dump() output."""
        compound = self._make_compound_id("user@example.com", "gcal-event-id", "acc-1")
        event = Event(id=compound)
        d = event.model_dump()
        assert d["calendar_uid"] == "gcal-event-id"

    def test_included_in_model_dump_by_alias(self) -> None:
        """calendar_uid appears in model_dump(by_alias=True) output."""
        compound = self._make_compound_id("user@example.com", "gcal-event-id", "acc-1")
        event = Event(id=compound)
        d = event.model_dump(by_alias=True)
        assert d["calendar_uid"] == "gcal-event-id"

    def test_none_in_model_dump_for_plain_id(self) -> None:
        """calendar_uid is None in model_dump() for non-compound IDs."""
        event = Event(id="simple-id")
        d = event.model_dump()
        assert d["calendar_uid"] is None

    def test_roundtrip_ignores_calendar_uid(self) -> None:
        """calendar_uid in input is ignored (it's computed, not stored)."""
        compound = self._make_compound_id("user@example.com", "the-gcal-id", "acc-1")
        d = {"id": compound, "calendar_uid": "should-be-ignored"}
        event = Event.model_validate(d)
        assert event.calendar_uid == "the-gcal-id"

    def test_real_morgen_id(self) -> None:
        """Decodes a realistic Morgen compound ID."""
        payload = json.dumps(["jeremy@example.com", "gd0vm7r3hk3s8vupk6ppra8th4", "673476aefe6a6bd01ba78a71"])
        compound = base64.b64encode(payload.encode()).decode()
        event = Event(id=compound)
        assert event.calendar_uid == "gd0vm7r3hk3s8vupk6ppra8th4"

    def test_unpadded_base64(self) -> None:
        """Morgen IDs often omit trailing '=' padding — must still decode."""
        payload = json.dumps(["jeremy@example.com", "gd0vm7r3hk3s8vupk6ppra8th4", "673476aefe6a6bd01ba78a71"])
        compound = base64.b64encode(payload.encode()).decode().rstrip("=")
        assert len(compound) % 4 != 0, "fixture should be unpadded"
        event = Event(id=compound)
        assert event.calendar_uid == "gd0vm7r3hk3s8vupk6ppra8th4"


class TestTaskModel:
    def test_valid_task(self) -> None:
        task = Task(id="task-1", title="Review PR", priority=2, tags=["tag-1"])
        assert task.id == "task-1"
        assert task.tags == ["tag-1"]

    def test_integration_id_defaults_to_morgen(self) -> None:
        task = Task(id="t1", title="Test")
        assert task.integrationId == "morgen"

    def test_external_task_with_labels_and_links(self) -> None:
        task = Task(
            id="linear-1",
            title="Budget",
            integrationId="linear",
            labels=[{"id": "state", "value": "in-progress"}],
            links={"original": {"href": "https://linear.app/...", "title": "Open"}},
        )
        assert task.integrationId == "linear"
        assert len(task.labels) == 1

    def test_model_dump_preserves_camelCase(self) -> None:
        task = Task(id="t1", title="Test", taskListId="inbox", integrationId="linear")
        d = task.model_dump()
        assert "taskListId" in d
        assert "integrationId" in d

    def test_extra_fields_ignored(self) -> None:
        task = Task(id="t1", title="Test", unknownField="x")
        assert not hasattr(task, "unknownField")

    def test_missing_required_field(self) -> None:
        with pytest.raises(ValidationError):
            Task()  # missing id


class TestTaskListResponse:
    def test_empty_response(self) -> None:
        resp = TaskListResponse()
        assert resp.tasks == []
        assert resp.labelDefs == []

    def test_with_data(self) -> None:
        resp = TaskListResponse(
            tasks=[Task(id="t1", title="Test")],
            labelDefs=[LabelDef(id="state", label="Status")],
            spaces=[Space(id="s1", name="Projects")],
        )
        assert len(resp.tasks) == 1
        assert len(resp.labelDefs) == 1
        assert len(resp.spaces) == 1


# ---------------------------------------------------------------------------
# API drift detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "fixture_file"),
    [
        (Account, "account_sample.json"),
        (Calendar, "calendar_sample.json"),
        (Event, "event_sample.json"),
        (Task, "task_sample.json"),
        (Tag, "tag_sample.json"),
    ],
)
def test_model_covers_api_fields(model: type, fixture_file: str) -> None:
    """Detect when the API returns fields we haven't modeled.

    Fails when a fixture has fields not in the model. To fix:
    1. Add the new field to the model
    2. Or remove from fixture if intentionally ignored
    """
    fixture_path = FIXTURES / fixture_file
    sample = json.loads(fixture_path.read_text())
    model_fields = set(model.model_fields.keys())

    # Include aliases (e.g., morgen_metadata -> morgen.so:metadata)
    for _field_name, field_info in model.model_fields.items():
        if field_info.alias:
            model_fields.add(field_info.alias)

    api_fields = set(sample.keys())
    new_fields = api_fields - model_fields
    assert not new_fields, (
        f"{model.__name__} doesn't model these API fields: {new_fields}. "
        f"Add them to the model or remove from fixture if intentionally ignored."
    )


# ---------------------------------------------------------------------------
# TaskList model tests
# ---------------------------------------------------------------------------


class TestTaskList:
    def test_from_api_response(self) -> None:
        data = {
            "@type": "TaskList",
            "serviceName": "morgen",
            "id": "07134c5c-1183-4f8c-9716-4c58257694c8@morgen.so",
            "name": "Run - Work",
            "color": "#38c2c7",
            "role": None,
            "position": 1761671965352,
            "created": "2025-10-28T17:19:25Z",
            "updated": "2025-10-28T17:19:32.616Z",
            "myRights": {"mayAdmin": True, "mayDelete": True},
            "accountId": None,
        }
        tl = TaskList.model_validate(data)
        assert tl.id == "07134c5c-1183-4f8c-9716-4c58257694c8@morgen.so"
        assert tl.name == "Run - Work"
        assert tl.color == "#38c2c7"
        assert tl.position == 1761671965352

    def test_inbox_role(self) -> None:
        data = {"id": "inbox", "name": "Inbox", "role": "inbox", "color": "#9695A0"}
        tl = TaskList.model_validate(data)
        assert tl.role == "inbox"

    def test_extra_fields_ignored(self) -> None:
        data = {"id": "test", "name": "Test", "myRights": {"mayAdmin": True}, "accountId": None}
        tl = TaskList.model_validate(data)
        assert tl.id == "test"


class TestTaskNewFields:
    def test_position_field(self) -> None:
        data = {"id": "t1", "title": "Test", "position": 1771922554998}
        task = Task.model_validate(data)
        assert task.position == 1771922554998

    def test_earliest_start_field(self) -> None:
        data = {"id": "t1", "title": "Test", "earliestStart": "2026-02-25T00:00:00"}
        task = Task.model_validate(data)
        assert task.earliestStart == "2026-02-25T00:00:00"

    def test_description_content_type_field(self) -> None:
        data = {"id": "t1", "title": "Test", "descriptionContentType": "text/plain"}
        task = Task.model_validate(data)
        assert task.descriptionContentType == "text/plain"

    def test_fields_optional_default_none(self) -> None:
        data = {"id": "t1", "title": "Test"}
        task = Task.model_validate(data)
        assert task.position is None
        assert task.earliestStart is None
        assert task.descriptionContentType is None

    def test_full_api_response(self) -> None:
        data = {
            "@type": "Task",
            "id": "548211d9-8b34-4265-ada9-575b22769d30",
            "taskListId": "inbox",
            "tags": [],
            "title": "Test for gm1",
            "description": "<ul><li><p>bullet</p></li></ul><p></p>",
            "descriptionContentType": "text/plain",
            "estimatedDuration": "PT60M",
            "priority": 1,
            "progress": "needs-action",
            "earliestStart": "2026-02-25T00:00:00",
            "position": 1771922554998,
            "created": "2026-02-24T08:42:41Z",
            "updated": "2026-02-24T08:43:14.547Z",
            "integrationId": "morgen",
        }
        task = Task.model_validate(data)
        assert task.position == 1771922554998
        assert task.earliestStart == "2026-02-25T00:00:00"
        assert task.descriptionContentType == "text/plain"

    def test_priority_range_nine(self) -> None:
        data = {"id": "t1", "title": "Test", "priority": 9}
        task = Task.model_validate(data)
        assert task.priority == 9
