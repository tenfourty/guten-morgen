"""Tests for lists commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from guten_morgen.cli import cli
from guten_morgen.client import MorgenClient


class TestListsList:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3
        assert data[0]["name"] == "Inbox"

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "list"])
        assert result.exit_code == 0
        assert "Run - Work" in result.output

    def test_concise(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "list", "--json", "--response-format", "concise"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "id" in data[0]
        assert "name" in data[0]


class TestListsCreate:
    def test_create(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "create", "--name", "Project: X"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "Project: X"

    def test_create_with_color(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "create", "--name", "Test", "--color", "#ff0000"])
        assert result.exit_code == 0


class TestListsUpdate:
    def test_update(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "update", "list-work@morgen.so", "--name", "Work Tasks"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "list-work@morgen.so"
        assert data["name"] == "Work Tasks"


class TestListsDelete:
    def test_delete(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["lists", "delete", "list-work@morgen.so"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "deleted"
