"""Tests for the `morgen groups` command and --group/--all-calendars options."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient


class TestGroupsCommand:
    def test_groups_json_output(self, runner: CliRunner) -> None:
        """Groups command outputs JSON with config info."""
        result = runner.invoke(cli, ["groups", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "config_file" in data
        assert "default_group" in data
        assert "active_only" in data
        assert "groups" in data

    def test_groups_with_config(self, runner: CliRunner, tmp_path: Path) -> None:
        """Groups command shows configured groups."""
        cfg = tmp_path / "config.toml"
        cfg.write_text("""\
default_group = "work"
active_only = true

[groups.work]
accounts = ["test@example.com:google"]
""")
        with patch("guten_morgen.cli.load_morgen_config") as mock_load:
            from guten_morgen.groups import load_morgen_config

            mock_load.return_value = load_morgen_config(cfg)
            result = runner.invoke(cli, ["groups", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["default_group"] == "work"
        assert data["active_only"] is True
        assert "work" in data["groups"]


class TestGroupFilterOption:
    def test_events_list_with_group_all(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--group all returns all events (no filtering)."""
        result = runner.invoke(
            cli,
            [
                "events",
                "list",
                "--start",
                "2026-02-17T00:00:00",
                "--end",
                "2026-02-17T23:59:59",
                "--json",
                "--group",
                "all",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 4  # same as unfiltered

    def test_next_with_group_all(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--group all works on next command."""
        result = runner.invoke(cli, ["next", "--json", "--group", "all"])
        assert result.exit_code == 0

    def test_today_with_group_all(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        """--group all works on today command."""
        result = runner.invoke(cli, ["today", "--json", "--group", "all"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "events" in data

    def test_unknown_group_errors(self, runner: CliRunner, tmp_path: Path, mock_client: MorgenClient) -> None:
        """Unknown group name produces an error."""
        cfg = tmp_path / "config.toml"
        cfg.write_text("[groups.work]\naccounts = ['a@b.com:google']\n")
        with patch("guten_morgen.cli.load_morgen_config") as mock_load:
            from guten_morgen.groups import load_morgen_config

            mock_load.return_value = load_morgen_config(cfg)
            result = runner.invoke(
                cli,
                [
                    "events",
                    "list",
                    "--start",
                    "2026-02-17T00:00:00",
                    "--end",
                    "2026-02-17T23:59:59",
                    "--json",
                    "--group",
                    "nope",
                ],
            )
        assert result.exit_code != 0
