"""Tests for bearer token auth."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from guten_morgen.auth import find_morgen_desktop_config, read_morgen_credentials


class TestFindMorgenDesktopConfig:
    def test_macos_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Finds config at ~/Library/Application Support/Morgen/config.json on macOS."""
        config_dir = tmp_path / "Library" / "Application Support" / "Morgen"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text('{"morgen-refresh-token": "tok", "morgen-device-id": "dev"}')
        monkeypatch.setenv("HOME", str(tmp_path))
        result = find_morgen_desktop_config()
        assert result == config_file

    def test_xdg_linux_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Finds config at $XDG_CONFIG_HOME/Morgen/config.json on Linux."""
        config_dir = tmp_path / "xdg" / "Morgen"
        config_dir.mkdir(parents=True)
        config_file = config_dir / "config.json"
        config_file.write_text('{"morgen-refresh-token": "tok", "morgen-device-id": "dev"}')
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
        # Ensure macOS path doesn't exist
        monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
        result = find_morgen_desktop_config()
        assert result == config_file

    def test_not_installed_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns None when Morgen desktop is not installed."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert find_morgen_desktop_config() is None


class TestReadMorgenCredentials:
    def test_reads_refresh_token_and_device_id(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "morgen-refresh-token": "my-refresh-token",
                    "morgen-device-id": "my-device-id",
                }
            )
        )
        creds = read_morgen_credentials(config_file)
        assert creds is not None
        assert creds == ("my-refresh-token", "my-device-id")

    def test_missing_refresh_token_returns_none(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"morgen-device-id": "dev"}))
        assert read_morgen_credentials(config_file) is None

    def test_missing_device_id_returns_none(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"morgen-refresh-token": "tok"}))
        assert read_morgen_credentials(config_file) is None

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text("not json {{{")
        assert read_morgen_credentials(config_file) is None

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert read_morgen_credentials(tmp_path / "nope.json") is None
