"""Tests for calendar group configuration and filter resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from morgen.errors import GroupNotFoundError
from morgen.groups import (
    GroupConfig,
    MorgenConfig,
    load_morgen_config,
    match_account,
    resolve_filter,
)


class TestLoadMorgenConfig:
    """Tests for load_morgen_config."""

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        config = load_morgen_config(tmp_path / "nonexistent.toml")
        assert config.default_group is None
        assert config.active_only is False
        assert config.groups == {}

    def test_parses_groups(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("""\
default_group = "work"
active_only = true

[groups.work]
accounts = ["test@example.com:google"]

[groups.family]
accounts = ["test@example.com:fastmail", "test@example.com:google"]
calendars = ["Family", "Personal"]
""")
        config = load_morgen_config(cfg_file)
        assert config.default_group == "work"
        assert config.active_only is True
        assert "work" in config.groups
        assert config.groups["work"].accounts == ["test@example.com:google"]
        assert config.groups["work"].calendars is None
        assert "family" in config.groups
        assert config.groups["family"].calendars == ["Family", "Personal"]

    def test_env_var_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg_file = tmp_path / "custom.toml"
        cfg_file.write_text("active_only = true\n")
        monkeypatch.setenv("MORGEN_CONFIG", str(cfg_file))
        config = load_morgen_config()
        assert config.active_only is True

    def test_empty_groups_section(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("active_only = true\n")
        config = load_morgen_config(cfg_file)
        assert config.active_only is True
        assert config.groups == {}


class TestResolveFilter:
    """Tests for resolve_filter."""

    def test_no_group_no_default(self) -> None:
        config = MorgenConfig()
        f = resolve_filter(config)
        assert f.account_keys is None
        assert f.calendar_names is None
        assert f.active_only is False

    def test_group_all(self) -> None:
        config = MorgenConfig(active_only=True)
        f = resolve_filter(config, group="all")
        assert f.account_keys is None
        assert f.calendar_names is None
        assert f.active_only is True

    def test_named_group(self) -> None:
        config = MorgenConfig(groups={"work": GroupConfig(accounts=["a@b.com:google"], calendars=["Work"])})
        f = resolve_filter(config, group="work")
        assert f.account_keys == ["a@b.com:google"]
        assert f.calendar_names == ["Work"]

    def test_unknown_group_raises(self) -> None:
        config = MorgenConfig(groups={"work": GroupConfig(accounts=["a@b.com:google"])})
        with pytest.raises(GroupNotFoundError, match="Unknown group 'nope'"):
            resolve_filter(config, group="nope")

    def test_default_group(self) -> None:
        config = MorgenConfig(
            default_group="work",
            groups={"work": GroupConfig(accounts=["a@b.com:google"])},
        )
        f = resolve_filter(config)
        assert f.account_keys == ["a@b.com:google"]

    def test_all_calendars_overrides_active_only(self) -> None:
        config = MorgenConfig(active_only=True)
        f = resolve_filter(config, all_calendars=True)
        assert f.active_only is False

    def test_active_only_propagated(self) -> None:
        config = MorgenConfig(
            active_only=True,
            groups={"work": GroupConfig(accounts=["a@b.com:google"])},
        )
        f = resolve_filter(config, group="work")
        assert f.active_only is True


class TestMatchAccount:
    """Tests for match_account."""

    def test_email_and_provider(self) -> None:
        account = {"preferredEmail": "test@example.com", "integrationId": "google"}
        assert match_account(account, "test@example.com:google") is True
        assert match_account(account, "test@example.com:caldav") is False

    def test_email_only(self) -> None:
        account = {"preferredEmail": "test@example.com", "integrationId": "google"}
        assert match_account(account, "test@example.com") is True

    def test_no_match(self) -> None:
        account = {"preferredEmail": "other@example.com", "integrationId": "google"}
        assert match_account(account, "test@example.com:google") is False

    def test_null_preferred_email_falls_back_to_emails_list(self) -> None:
        """Google accounts often have preferredEmail=null; match via emails list."""
        account = {
            "preferredEmail": None,
            "emails": ["user@example.com", "group@calendar.google.com"],
            "integrationId": "google",
        }
        assert match_account(account, "user@example.com:google") is True
        assert match_account(account, "user@example.com") is True
        assert match_account(account, "nobody@example.com:google") is False

    def test_emails_list_with_provider_mismatch(self) -> None:
        account = {
            "preferredEmail": None,
            "emails": ["user@example.com"],
            "integrationId": "google",
        }
        assert match_account(account, "user@example.com:caldav") is False
