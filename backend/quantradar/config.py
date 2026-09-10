"""QuantRadar 配置。

InvestmentDataProvider 的配置由 QuantRadar 自行管理，不写入 BulletTrade 的
`utils/env_loader.py`。默认本地环境指向 investment_data 的 Dolt SQL server（只读）。

环境变量（均带 INVESTMENT_DATA_ 前缀，避免与 BulletTrade 内置配置冲突）：
    INVESTMENT_DATA_HOST     默认 127.0.0.1
    INVESTMENT_DATA_PORT     默认 3307
    INVESTMENT_DATA_USER     默认 root
    INVESTMENT_DATA_PASSWORD 默认空（本地 Dolt 通常无需密码）
    INVESTMENT_DATA_DATABASE 默认 investment_data
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class InvestmentDataConfig:
    """InvestmentDataProvider 连接与行为配置（不可变）。"""

    host: str = "127.0.0.1"
    port: int = 3307
    user: str = "root"
    password: str = ""
    database: str = "investment_data"
    connect_timeout: float = 5.0
    read_timeout: float = 120.0

    def as_pymysql_kwargs(self) -> dict:
        """构造 pymysql.connect 所需的关键字参数（不含写操作相关项）。"""
        return {
            "host": self.host,
            "port": int(self.port),
            "user": self.user,
            "password": self.password,
            "database": self.database,
            "connect_timeout": self.connect_timeout,
            "read_timeout": self.read_timeout,
            "charset": "utf8mb4",
        }


@dataclass(frozen=True)
class DataHubConfig:
    """Locations and read endpoints for the versioned supplemental data store."""

    base_database: str = "investment_data"
    supplemental_database: str = "quantradar_data"
    base_host: str = "127.0.0.1"
    base_port: int = 3307
    supplemental_host: str = "127.0.0.1"
    supplemental_port: int = 3308
    user: str = "root"
    password: str = ""
    supplemental_repo: str = "/data/quantradar_data"
    release_root: str = "/data/quantradar_data/releases"
    raw_root: str = "/data/quantradar_data/raw-artifacts"
    journal_root: str = "/data/quantradar_data/journals"
    sw_ca_bundle: str | None = None
    baostock_host: str | None = None
    fetch_workers: int = 1
    connect_timeout: float = 5.0
    read_timeout: float = 120.0


def load_datahub_config() -> DataHubConfig:
    """Load DataHub settings without ever reusing the base database for writes."""

    def _int(key: str, default: int) -> int:
        try:
            return int(os.environ.get(key, default))
        except ValueError:
            return default

    def _float(key: str, default: float) -> float:
        try:
            return float(os.environ.get(key, default))
        except ValueError:
            return default

    return DataHubConfig(
        base_database=os.environ.get("DATAHUB_BASE_DATABASE", "investment_data"),
        supplemental_database=os.environ.get("DATAHUB_SUPPLEMENTAL_DATABASE", "quantradar_data"),
        base_host=os.environ.get("DATAHUB_BASE_HOST", "127.0.0.1"),
        base_port=_int("DATAHUB_BASE_PORT", 3307),
        supplemental_host=os.environ.get("DATAHUB_SUPPLEMENTAL_HOST", "127.0.0.1"),
        supplemental_port=_int("DATAHUB_SUPPLEMENTAL_PORT", 3308),
        user=os.environ.get("DATAHUB_USER", "root"),
        password=os.environ.get("DATAHUB_PASSWORD", ""),
        supplemental_repo=os.environ.get("DATAHUB_SUPPLEMENTAL_REPO", "/data/quantradar_data"),
        release_root=os.environ.get("DATAHUB_RELEASE_ROOT", "/data/quantradar_data/releases"),
        raw_root=os.environ.get("DATAHUB_RAW_ROOT", "/data/quantradar_data/raw-artifacts"),
        journal_root=os.environ.get("DATAHUB_JOURNAL_ROOT", "/data/quantradar_data/journals"),
        sw_ca_bundle=os.environ.get("DATAHUB_SW_CA_BUNDLE") or None,
        baostock_host=os.environ.get("DATAHUB_BAOSTOCK_HOST") or None,
        fetch_workers=max(1, _int("DATAHUB_FETCH_WORKERS", 1)),
        connect_timeout=_float("DATAHUB_CONNECT_TIMEOUT", 5.0),
        read_timeout=_float("DATAHUB_READ_TIMEOUT", 120.0),
    )


def load_investment_data_config() -> InvestmentDataConfig:
    """从环境变量加载 InvestmentDataConfig；未设置时使用本地默认值。

    注意：不在本函数内硬编码任何真实密码；默认值 password="" 仅适用于
    本地无密码 Dolt。生产/远端环境应通过 .env 或环境变量显式提供。
    """

    def _int(key: str, default: int) -> int:
        raw = os.environ.get(key)
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    def _float(key: str, default: float) -> float:
        raw = os.environ.get(key)
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    return InvestmentDataConfig(
        host=os.environ.get("INVESTMENT_DATA_HOST", "127.0.0.1"),
        port=_int("INVESTMENT_DATA_PORT", 3307),
        user=os.environ.get("INVESTMENT_DATA_USER", "root"),
        password=os.environ.get("INVESTMENT_DATA_PASSWORD", ""),
        database=os.environ.get("INVESTMENT_DATA_DATABASE", "investment_data"),
        connect_timeout=_float("INVESTMENT_DATA_CONNECT_TIMEOUT", 5.0),
        read_timeout=_float("INVESTMENT_DATA_READ_TIMEOUT", 120.0),
    )
