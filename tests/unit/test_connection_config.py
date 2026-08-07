"""config.py / connection.py 单元测试（连接探针需数据库；不可达则跳过）。"""

import pytest

from quantradar.config import InvestmentDataConfig, load_investment_data_config
from quantradar.providers.investment_data.connection import (
    InvestmentDataConnection,
    InvestmentDataConnectionError,
)


@pytest.mark.unit
class TestConfig:
    def test_defaults(self):
        cfg = InvestmentDataConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 3307
        assert cfg.database == "investment_data"
        assert cfg.user == "root"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("INVESTMENT_DATA_HOST", "db.example.com")
        monkeypatch.setenv("INVESTMENT_DATA_PORT", "4006")
        monkeypatch.setenv("INVESTMENT_DATA_PASSWORD", "secret")
        cfg = load_investment_data_config()
        assert cfg.host == "db.example.com"
        assert cfg.port == 4006
        assert cfg.password == "secret"

    def test_pymysql_kwargs(self):
        kwargs = InvestmentDataConfig(port=3307).as_pymysql_kwargs()
        assert kwargs["port"] == 3307
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["charset"] == "utf8mb4"
        # 不得包含任何写操作相关参数
        assert "autocommit" not in kwargs or kwargs.get("autocommit") is False


@pytest.mark.unit
class TestConnectionCheck:
    def test_check_reachable(self, db_connection):
        info = db_connection.check()
        assert info["database"] == "investment_data"
        assert "ts_trade_day_calendar" in info["reachable_tables"]

    def test_unreachable_raises(self):
        cfg = InvestmentDataConfig(host="127.0.0.1", port=9)  # 几乎肯定无服务
        conn = InvestmentDataConnection(cfg)
        with pytest.raises(InvestmentDataConnectionError):
            conn.check()

    def test_query_readonly(self, db_connection):
        rows = db_connection.query(
            "SELECT COUNT(*) AS n FROM ts_a_stock_list"
        )
        assert rows and "n" in rows[0]
