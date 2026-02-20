"""Tests for tags commands."""

from __future__ import annotations

import json

from click.testing import CliRunner

from morgen.cli import cli
from morgen.client import MorgenClient


class TestTagsList:
    def test_json_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tags", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["name"] == "urgent"

    def test_table_output(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tags", "list"])
        assert result.exit_code == 0
        assert "urgent" in result.output

    def test_concise(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tags", "list", "--json", "--response-format", "concise"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "id" in data[0]
        assert "color" not in data[0]
        # Verify expected concise fields are present
        assert "name" in data[0]


class TestTagsGet:
    def test_get(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tags", "get", "tag-1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "id" in data


class TestTagsCreate:
    def test_create(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tags", "create", "--name", "work"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "work"

    def test_create_with_color(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tags", "create", "--name", "focus", "--color", "#0000ff"])
        assert result.exit_code == 0


class TestTagsUpdate:
    def test_update(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tags", "update", "tag-1", "--name", "critical"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "tag-1"
        assert data["name"] == "critical"


class TestTagsDelete:
    def test_delete(self, runner: CliRunner, mock_client: MorgenClient) -> None:
        result = runner.invoke(cli, ["tags", "delete", "tag-1"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "deleted"
        assert data["id"] == "tag-1"
