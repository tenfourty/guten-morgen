"""Tests for bearer token auth."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from guten_morgen.auth import (
    _load_cached_token,
    _refresh_access_token,
    _save_cached_token,
    find_morgen_desktop_config,
    get_bearer_token,
    read_morgen_credentials,
)


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


class TestRefreshAccessToken:
    def test_successful_refresh(self) -> None:
        """POST to /identity/refresh returns an access token."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "token": "fresh-access-token",
            "expiresIn": 3600,
        }
        with patch("guten_morgen.auth.httpx.post", return_value=mock_response) as mock_post:
            result = _refresh_access_token("refresh-tok", "device-123")
        assert result is not None
        token, expires_at = result
        assert token == "fresh-access-token"
        assert expires_at > time.time()
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[1]["json"]["refreshToken"] == "refresh-tok"
        assert call_kwargs[1]["json"]["deviceId"] == "device-123"

    def test_http_error_returns_none(self) -> None:
        """Non-200 response returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        with patch("guten_morgen.auth.httpx.post", return_value=mock_response):
            assert _refresh_access_token("bad-tok", "dev") is None

    def test_network_error_returns_none(self) -> None:
        """Network exception returns None."""
        with patch("guten_morgen.auth.httpx.post", side_effect=Exception("timeout")):
            assert _refresh_access_token("tok", "dev") is None


class TestTokenCache:
    def test_save_and_load(self, tmp_path: Path) -> None:
        """Saved token can be loaded back."""
        _save_cached_token(tmp_path, "my-token", time.time() + 3600)
        result = _load_cached_token(tmp_path)
        assert result is not None
        assert result[0] == "my-token"

    def test_expired_token_returns_none(self, tmp_path: Path) -> None:
        """Expired cached token is not returned."""
        _save_cached_token(tmp_path, "old-token", time.time() - 10)
        assert _load_cached_token(tmp_path) is None

    def test_missing_cache_returns_none(self, tmp_path: Path) -> None:
        """Missing cache file returns None."""
        assert _load_cached_token(tmp_path) is None

    def test_corrupt_cache_returns_none(self, tmp_path: Path) -> None:
        """Corrupt cache file returns None."""
        cache_file = tmp_path / "_bearer.json"
        cache_file.write_text("not json")
        assert _load_cached_token(tmp_path) is None

    def test_cache_file_has_restricted_permissions(self, tmp_path: Path) -> None:
        """Cache file is owner-only (0600) to protect the token."""
        _save_cached_token(tmp_path, "secret-token", time.time() + 3600)
        cache_file = tmp_path / "_bearer.json"
        mode = cache_file.stat().st_mode & 0o777
        assert mode == 0o600


class TestGetBearerToken:
    def test_returns_cached_token(self, tmp_path: Path) -> None:
        """Returns cached token when it's still valid."""
        _save_cached_token(tmp_path, "cached-token", time.time() + 3600)
        with patch("guten_morgen.auth.find_morgen_desktop_config", return_value=None):
            result = get_bearer_token(tmp_path)
        assert result == "cached-token"

    def test_refreshes_expired_token(self, tmp_path: Path) -> None:
        """Refreshes when cached token is expired."""
        config_file = tmp_path / "morgen-config.json"
        config_file.write_text(
            json.dumps(
                {
                    "morgen-refresh-token": "refresh-tok",
                    "morgen-device-id": "device-123",
                }
            )
        )
        with (
            patch("guten_morgen.auth.find_morgen_desktop_config", return_value=config_file),
            patch(
                "guten_morgen.auth._refresh_access_token",
                return_value=("new-token", time.time() + 3600),
            ),
        ):
            result = get_bearer_token(tmp_path)
        assert result == "new-token"

    def test_no_desktop_app_returns_none(self, tmp_path: Path) -> None:
        """Returns None when desktop app is not installed."""
        with patch("guten_morgen.auth.find_morgen_desktop_config", return_value=None):
            assert get_bearer_token(tmp_path) is None

    def test_refresh_failure_returns_none(self, tmp_path: Path) -> None:
        """Returns None when token refresh fails."""
        config_file = tmp_path / "morgen-config.json"
        config_file.write_text(
            json.dumps(
                {
                    "morgen-refresh-token": "refresh-tok",
                    "morgen-device-id": "device-123",
                }
            )
        )
        with (
            patch("guten_morgen.auth.find_morgen_desktop_config", return_value=config_file),
            patch("guten_morgen.auth._refresh_access_token", return_value=None),
        ):
            assert get_bearer_token(tmp_path) is None
