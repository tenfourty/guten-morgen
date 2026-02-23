"""Tests for gm init command."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from guten_morgen.cli import cli


class TestInit:
    def test_creates_xdg_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        xdg = tmp_path / "config"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["init"], input="test-api-key-123\n")

        assert result.exit_code == 0
        cfg_path = xdg / "guten-morgen" / "config.toml"
        assert cfg_path.exists()
        content = cfg_path.read_text()
        assert 'api_key = "test-api-key-123"' in content

    def test_refuses_overwrite_without_force(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        xdg = tmp_path / "config"
        gm_dir = xdg / "guten-morgen"
        gm_dir.mkdir(parents=True)
        existing = gm_dir / "config.toml"
        existing.write_text('api_key = "old"\n')
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["init"], input="new-key\n")

        assert result.exit_code == 1
        assert "already exists" in result.output
        assert existing.read_text() == 'api_key = "old"\n'

    def test_force_overwrites(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        xdg = tmp_path / "config"
        gm_dir = xdg / "guten-morgen"
        gm_dir.mkdir(parents=True)
        existing = gm_dir / "config.toml"
        existing.write_text('api_key = "old"\n')
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["init", "--force"], input="new-key\n")

        assert result.exit_code == 0
        content = existing.read_text()
        assert 'api_key = "new-key"' in content

    def test_output_path_shown(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        xdg = tmp_path / "config"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["init"], input="key\n")

        assert result.exit_code == 0
        assert "guten-morgen/config.toml" in result.output

    def test_written_config_is_valid_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Config written by init can be parsed as valid TOML."""
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]

        xdg = tmp_path / "config"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(cli, ["init"], input="my-key\n")
        assert result.exit_code == 0

        cfg_path = xdg / "guten-morgen" / "config.toml"
        with open(cfg_path, "rb") as f:
            data = tomllib.load(f)
        assert data["api_key"] == "my-key"
