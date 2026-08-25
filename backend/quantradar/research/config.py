"""Configuration for the isolated Research MVP runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _required_absolute(path: Path, name: str) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute path")
    return path


@dataclass(frozen=True)
class ResearchSettings:
    database_url: str
    data_dir: Path
    qyj_profile_dir: Path
    mineru_api_url: str = "http://127.0.0.1:58000"
    mineru_timeout_seconds: int = 1800
    mineru_concurrency: int = 1
    agnes_base_url: str = "https://apihub.agnes-ai.com/v1"
    agnes_api_key: str = ""
    agnes_model: str = "agnes-2.5-flash"
    agnes_max_input_tokens: int = 12000
    agnes_rpm: int = 19
    feishu_required_keyword: str = ""
    feishu_webhook_url: str = ""

    def __post_init__(self) -> None:
        if not self.database_url:
            raise ValueError("database_url is required")
        _required_absolute(self.data_dir, "data_dir")
        _required_absolute(self.qyj_profile_dir, "qyj_profile_dir")
        if self.mineru_concurrency != 1:
            raise ValueError("mineru_concurrency must be 1 for the MVP")

    @classmethod
    def from_env(cls) -> "ResearchSettings":
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
        database_url = os.environ.get("QUANTRADAR_RESEARCH_DATABASE_URL") or os.environ.get("QUANT_RADAR_PG_URL", "")
        return cls(
            database_url=database_url,
            data_dir=Path(os.environ.get("QUANTRADAR_RESEARCH_DATA_DIR", "/data/quantradar/research")),
            qyj_profile_dir=Path(os.environ.get("QUANTRADAR_QYJ_PROFILE_DIR", "/data/quantradar/qyj-profile")),
            mineru_api_url=os.environ.get("QUANTRADAR_MINERU_API_URL", "http://127.0.0.1:58000"),
            mineru_timeout_seconds=int(os.environ.get("QUANTRADAR_MINERU_TIMEOUT_SECONDS", "1800")),
            agnes_base_url=os.environ.get("QUANTRADAR_AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1"),
            agnes_api_key=os.environ.get("QUANTRADAR_AGNES_API_KEY", ""),
            agnes_model=os.environ.get("QUANTRADAR_AGNES_MODEL", "agnes-2.5-flash"),
            agnes_max_input_tokens=int(os.environ.get("QUANTRADAR_AGNES_MAX_INPUT_TOKENS", "12000")),
            agnes_rpm=int(os.environ.get("QUANTRADAR_AGNES_RPM", "19")),
            feishu_required_keyword=os.environ.get("QUANTRADAR_FEISHU_REQUIRED_KEYWORD", ""),
            feishu_webhook_url=os.environ.get("QUANTRADAR_FEISHU_WEBHOOK_URL", ""),
        )

    def ensure_directories(self) -> None:
        for relative in ("raw/metadata", "raw/pdf", "source_md", "analysis", "digest", "debug", "logs"):
            (self.data_dir / relative).mkdir(parents=True, exist_ok=True, mode=0o700)
        self.qyj_profile_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
