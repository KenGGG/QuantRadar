from pathlib import Path

import pytest


def test_settings_reject_relative_data_and_profile_directories(tmp_path: Path) -> None:
    """A relative artifact/profile path could place private files in Git."""
    from quantradar.research.config import ResearchSettings

    with pytest.raises(ValueError, match="absolute"):
        ResearchSettings(
            database_url="sqlite+pysqlite:///:memory:",
            data_dir=Path("research-data"),
            qyj_profile_dir=tmp_path / "profile",
        )


def test_settings_loads_agnes_and_feishu_secrets_from_environment(tmp_path: Path, monkeypatch) -> None:
    """Runtime configuration must expose supplied secrets without embedding them in code."""
    from quantradar.research.config import ResearchSettings

    monkeypatch.setenv("QUANTRADAR_RESEARCH_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("QUANTRADAR_RESEARCH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("QUANTRADAR_QYJ_PROFILE_DIR", str(tmp_path / "profile"))
    monkeypatch.setenv("QUANTRADAR_AGNES_API_KEY", "test-agnes-key")
    monkeypatch.setenv("QUANTRADAR_FEISHU_WEBHOOK_URL", "https://example.test/webhook")

    settings = ResearchSettings.from_env()

    assert settings.agnes_api_key == "test-agnes-key"
    assert settings.feishu_webhook_url == "https://example.test/webhook"

    with pytest.raises(ValueError, match="absolute"):
        ResearchSettings(
            database_url="sqlite+pysqlite:///:memory:",
            data_dir=tmp_path / "research-data",
            qyj_profile_dir=Path("profile"),
        )
