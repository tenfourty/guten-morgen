"""Tests for availability command."""

from __future__ import annotations

import json

from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient


class TestAvailability:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["availability", "--date", "2026-02-17", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0
        assert "start" in data[0]
        assert "end" in data[0]
        assert "duration_minutes" in data[0]

    def test_custom_window(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(
            cli, ["availability", "--date", "2026-02-17", "--start", "10:00", "--end", "14:00", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_custom_min_duration(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["availability", "--date", "2026-02-17", "--min-duration", "60", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for slot in data:
            assert slot["duration_minutes"] >= 60

    def test_date_required(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["availability", "--json"])
        assert result.exit_code != 0

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["availability", "--date", "2026-02-17"])
        assert result.exit_code == 0
