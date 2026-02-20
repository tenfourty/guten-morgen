"""Tests for configuration loading."""

from __future__ import annotations

import pytest

from guten_morgen.config import Settings, load_settings
from guten_morgen.errors import ConfigError


class TestSettings:
    def test_dataclass_defaults(self) -> None:
        s = Settings(api_key="test-key")
        assert s.api_key == "test-key"
        assert s.base_url == "https://api.morgen.so/v3"
        assert s.timeout == 30.0


class TestLoadSettings:
    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MORGEN_API_KEY", "test-key-123")
        settings = load_settings()
        assert settings.api_key == "test-key-123"

    def test_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MORGEN_API_KEY", raising=False)
        # Prevent .env file from being loaded
        monkeypatch.setattr("guten_morgen.config._find_env_file", lambda: None)
        with pytest.raises(ConfigError, match="MORGEN_API_KEY is not set"):
            load_settings()

    def test_custom_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MORGEN_API_KEY", "key")
        monkeypatch.setenv("MORGEN_BASE_URL", "https://custom.api.com")
        settings = load_settings()
        assert settings.base_url == "https://custom.api.com"

    def test_custom_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MORGEN_API_KEY", "key")
        monkeypatch.setenv("MORGEN_TIMEOUT", "60.0")
        settings = load_settings()
        assert settings.timeout == 60.0
