"""InvestmentDataProvider 的只读数据库连接。

设计约束（见 docs/03 配置边界与 docs/00 核心原则）：
    - 只读语义：本连接只执行 SELECT，绝不 INSERT/UPDATE/DELETE/ALTER/DDL。
    - 超时：connect_timeout / read_timeout 显式传入。
    - 明确错误：连接/查询失败抛出 InvestmentDataConnectionError（含上下文）。
    - 连接检查：check() 执行轻量探针，供 bootstrap 验证连通性。
    - best-effort 只读会话：尝试 SET SESSION TRANSACTION READ ONLY；不支持则忽略，
      真正的写保护依赖「本 Provider 不发出任何写语句」这一纪律。

禁止在本文件中引入任何写操作能力。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pymysql
from pymysql.cursors import DictCursor

from ...config import InvestmentDataConfig


class InvestmentDataConnectionError(Exception):
    """investment_data 连接或查询失败（只读语义下）。"""


class InvestmentDataConnection:
    """基于 pymysql 的只读连接管理器。

    每次查询通过 `query` / `query_one` 复用单条连接；连接在使用前会探测存活，
    失效则重建。所有访问最终都走 SELECT。
    """

    def __init__(self, config: InvestmentDataConfig) -> None:
        self._config = config
        self._conn: Optional[pymysql.connections.Connection] = None

    # -- 连接生命周期 ----------------------------------------------------

    def _new_connection(self) -> pymysql.connections.Connection:
        try:
            conn = pymysql.connect(**self._config.as_pymysql_kwargs(), cursorclass=DictCursor)
        except pymysql.MySQLError as exc:  # pragma: no cover - 依赖真实 DB
            raise InvestmentDataConnectionError(
                f"无法连接 investment_data（{self._config.host}:{self._config.port}"
                f"/{self._config.database}）：{exc}"
            ) from exc
        # best-effort 只读会话；Dolt/MySQL 不支持时静默忽略，写保护靠纪律保证
        try:
            with conn.cursor() as cur:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
        except pymysql.MySQLError:
            pass
        return conn

    def _ensure_connection(self) -> pymysql.connections.Connection:
        if self._conn is None or not self._is_alive(self._conn):
            if self._conn is not None:
                try:
                    self._conn.close()
                except pymysql.MySQLError:
                    pass
                self._conn = None
            self._conn = self._new_connection()
        return self._conn

    @staticmethod
    def _is_alive(conn: pymysql.connections.Connection) -> bool:
        try:
            conn.ping(reconnect=False)
            return True
        except pymysql.MySQLError:
            return False

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except pymysql.MySQLError:
                pass
            self._conn = None

    # -- 探针 ------------------------------------------------------------

    def check(self) -> Dict[str, Any]:
        """连接探针：验证可连通、目标库存在、关键表可访问。

        返回包含版本/库名/样本表行数的字典；失败抛 InvestmentDataConnectionError。
        仅使用 SELECT / 只读信息_schema 查询。
        """
        try:
            with self._ensure_connection().cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
                cur.execute("SELECT DATABASE() AS db")
                db = cur.fetchone()["db"]
                cur.execute(
                    "SELECT TABLE_NAME FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = %s AND TABLE_NAME IN "
                    "(%s,%s,%s,%s,%s)",
                    (
                        self._config.database,
                        "ts_trade_day_calendar",
                        "ts_a_stock_list",
                        "ts_index_weight",
                        "final_a_stock_eod_price",
                        "bao_a_stock_eod_info",
                    ),
                )
                tables = {r["TABLE_NAME"] for r in cur.fetchall()}
        except pymysql.MySQLError as exc:  # pragma: no cover - 依赖真实 DB
            raise InvestmentDataConnectionError(f"连接探针失败：{exc}") from exc

        required = {
            "ts_trade_day_calendar",
            "ts_a_stock_list",
            "ts_index_weight",
            "final_a_stock_eod_price",
        }
        missing = required - tables
        if missing:
            raise InvestmentDataConnectionError(
                f"investment_data 缺少必要表：{sorted(missing)}"
            )
        return {"database": db, "reachable_tables": sorted(tables)}

    # -- 查询（只读） ----------------------------------------------------

    def query(self, sql: str, args: Optional[Sequence[Any]] = None) -> List[Dict[str, Any]]:
        """执行只读 SELECT，返回字典行列表。"""
        try:
            with self._ensure_connection().cursor() as cur:
                cur.execute(sql, args or ())
                return list(cur.fetchall())
        except pymysql.MySQLError as exc:  # pragma: no cover - 依赖真实 DB
            raise InvestmentDataConnectionError(f"查询失败：{exc}\nSQL={sql}") from exc

    def query_one(self, sql: str, args: Optional[Sequence[Any]] = None) -> Optional[Dict[str, Any]]:
        rows = self.query(sql, args)
        return rows[0] if rows else None

    def query_scalar(self, sql: str, args: Optional[Sequence[Any]] = None) -> Any:
        row = self.query_one(sql, args)
        if row is None:
            return None
        return next(iter(row.values()))


def connect(config: InvestmentDataConfig) -> InvestmentDataConnection:
    """便捷工厂：创建一个已通过 check() 的连接。"""
    conn = InvestmentDataConnection(config)
    conn.check()
    return conn
