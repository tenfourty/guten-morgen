"""Tests for Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from morgen.models import Account, Calendar, Tag


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
