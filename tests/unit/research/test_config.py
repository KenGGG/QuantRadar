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

    with pytest.raises(ValueError, match="absolute"):
        ResearchSettings(
            database_url="sqlite+pysqlite:///:memory:",
            data_dir=tmp_path / "research-data",
            qyj_profile_dir=Path("profile"),
        )

