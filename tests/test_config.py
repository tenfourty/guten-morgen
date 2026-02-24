"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from guten_morgen.config import Settings, find_config, load_settings
from guten_morgen.errors import ConfigError


class TestSettings:
    def test_dataclass_defaults(self) -> None:
        s = Settings(api_key="test-key")
        assert s.api_key == "test-key"
        assert s.base_url == "https://api.morgen.so/v3"
        assert s.timeout == 30.0


class TestFindConfig:
    def test_gm_config_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / "custom.toml"
        cfg.write_text("api_key = 'test'\n")
        monkeypatch.setenv("GM_CONFIG", str(cfg))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert find_config() == cfg

    def test_gm_config_env_var_missing_file_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GM_CONFIG", str(tmp_path / "nope.toml"))
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        with pytest.raises(ConfigError, match="GM_CONFIG points to missing file"):
            find_config()

    def test_project_config_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / "guten-morgen.toml"
        cfg.write_text("api_key = 'test'\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert find_config() == cfg

    def test_project_config_walk_up(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / "guten-morgen.toml"
        cfg.write_text("api_key = 'test'\n")
        subdir = tmp_path / "sub" / "deep"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        assert find_config() == cfg

    def test_xdg_config_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        xdg = tmp_path / "xdg"
        gm_dir = xdg / "guten-morgen"
        gm_dir.mkdir(parents=True)
        cfg = gm_dir / "config.toml"
        cfg.write_text("api_key = 'test'\n")
        monkeypatch.chdir(tmp_path)  # no config.toml in CWD
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        assert find_config() == cfg

    def test_xdg_default_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        home = tmp_path / "fakehome"
        gm_dir = home / ".config" / "guten-morgen"
        gm_dir.mkdir(parents=True)
        cfg = gm_dir / "config.toml"
        cfg.write_text("api_key = 'test'\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", str(home))
        assert find_config() == cfg

    def test_no_config_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "emptyhome"))
        assert find_config() is None

    def test_priority_gm_config_over_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_cfg = tmp_path / "env.toml"
        env_cfg.write_text("api_key = 'from-env'\n")
        cwd_cfg = tmp_path / "config.toml"
        cwd_cfg.write_text("api_key = 'from-cwd'\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("GM_CONFIG", str(env_cfg))
        assert find_config() == env_cfg

    def test_priority_project_over_xdg(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project_cfg = tmp_path / "guten-morgen.toml"
        project_cfg.write_text("api_key = 'from-project'\n")
        xdg = tmp_path / "xdg"
        gm_dir = xdg / "guten-morgen"
        gm_dir.mkdir(parents=True)
        (gm_dir / "config.toml").write_text("api_key = 'from-xdg'\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        assert find_config() == project_cfg


class TestSettingsMaxRetries:
    def test_default_max_retries(self) -> None:
        s = Settings(api_key="k")
        assert s.max_retries == 2

    def test_custom_max_retries(self) -> None:
        s = Settings(api_key="k", max_retries=5)
        assert s.max_retries == 5


class TestLoadSettings:
    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MORGEN_API_KEY", "test-key-123")
        settings = load_settings()
        assert settings.api_key == "test-key-123"

    def test_from_config_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text('api_key = "toml-key-456"\n')
        monkeypatch.setenv("GM_CONFIG", str(cfg))
        monkeypatch.delenv("MORGEN_API_KEY", raising=False)
        settings = load_settings()
        assert settings.api_key == "toml-key-456"

    def test_env_overrides_toml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / "config.toml"
        cfg.write_text('api_key = "toml-key"\n')
        monkeypatch.setenv("GM_CONFIG", str(cfg))
        monkeypatch.setenv("MORGEN_API_KEY", "env-key")
        settings = load_settings()
        assert settings.api_key == "env-key"

    def test_missing_key_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MORGEN_API_KEY", raising=False)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
        with pytest.raises(ConfigError, match="MORGEN_API_KEY is not set"):
            load_settings()

    def test_missing_key_suggests_gm_init(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MORGEN_API_KEY", raising=False)
        monkeypatch.delenv("GM_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
        with pytest.raises(ConfigError) as exc_info:
            load_settings()
        assert "gm init" in exc_info.value.suggestions[0]

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


class TestBearerTokenInSettings:
    def test_settings_has_bearer_token_field(self) -> None:
        s = Settings(api_key="test-key")
        assert s.bearer_token is None

    def test_settings_accepts_bearer_token(self) -> None:
        s = Settings(api_key="test-key", bearer_token="my-bearer")
        assert s.bearer_token == "my-bearer"

    def test_load_settings_populates_bearer_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import patch

        monkeypatch.setenv("MORGEN_API_KEY", "test-key")
        with patch("guten_morgen.auth.get_bearer_token", return_value="desktop-token"):
            settings = load_settings()
        assert settings.bearer_token == "desktop-token"
        assert settings.api_key == "test-key"

    def test_load_settings_bearer_none_when_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import patch

        monkeypatch.setenv("MORGEN_API_KEY", "test-key")
        with patch("guten_morgen.auth.get_bearer_token", return_value=None):
            settings = load_settings()
        assert settings.bearer_token is None

    def test_morgen_bearer_token_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """$MORGEN_BEARER_TOKEN env var overrides desktop app token."""
        from unittest.mock import patch

        monkeypatch.setenv("MORGEN_API_KEY", "test-key")
        monkeypatch.setenv("MORGEN_BEARER_TOKEN", "env-bearer")
        with patch("guten_morgen.auth.get_bearer_token", return_value="desktop-token"):
            settings = load_settings()
        assert settings.bearer_token == "env-bearer"
