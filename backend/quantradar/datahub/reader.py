"""Resolve a release once, then bind both Dolt reads to its immutable commits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..config import DataHubConfig, InvestmentDataConfig
from .release import ReleaseStore


@dataclass(frozen=True)
class ReleaseReadScope:
    release_id: str
    base_database: str
    supplemental_database: str | None
    manifest: dict


class ReleaseReader:
    def __init__(self, config: DataHubConfig) -> None:
        self.config = config
        self.releases = ReleaseStore(config.release_root)

    def resolve(self, release_id: str | None = None) -> ReleaseReadScope:
        manifest = self.releases.resolve(release_id)
        return ReleaseReadScope(
            release_id=manifest["release_id"],
            base_database=f"{self.config.base_database}/{manifest['base_commit']}",
            supplemental_database=f"{self.config.supplemental_database}/{manifest['supplemental_commit']}" if manifest.get('supplemental_commit') else None,
            manifest=manifest,
        )

    def base_config(self, scope: ReleaseReadScope) -> InvestmentDataConfig:
        """Return an immutable base configuration pointed at the release commit."""
        return InvestmentDataConfig(
            host=self.config.base_host,
            port=self.config.base_port,
            user=self.config.user,
            password=self.config.password,
            database=scope.base_database,
            connect_timeout=self.config.connect_timeout,
            read_timeout=self.config.read_timeout,
        )

    def supplemental_connection_kwargs(self, scope: ReleaseReadScope) -> dict:
        """Pymysql arguments for a read-only commit-qualified supplemental connection."""
        if scope.supplemental_database is None:
            raise ValueError('此版本仅提供基础行情，补充字段不可用')
        return {
            "host": self.config.supplemental_host,
            "port": self.config.supplemental_port,
            "user": self.config.user,
            "password": self.config.password,
            "database": scope.supplemental_database,
            "connect_timeout": self.config.connect_timeout,
            "read_timeout": self.config.read_timeout,
            "charset": "utf8mb4",
        }

    def base_connection(self, scope: ReleaseReadScope):
        from ..providers.investment_data.connection import InvestmentDataConnection

        return InvestmentDataConnection(self.base_config(scope))

    def supplemental_reader(self, scope: ReleaseReadScope) -> "SupplementalReader":
        import pymysql
        from pymysql.cursors import DictCursor

        kwargs = self.supplemental_connection_kwargs(scope)
        return SupplementalReader(lambda: pymysql.connect(**kwargs, cursorclass=DictCursor))


class SupplementalReader:
    """Read only a commit-qualified supplemental connection supplied by ReleaseReader."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    def valuation(
        self, symbol: str, start_date: str, end_date: str, *, required_fields: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        allowed = {"pe_ttm", "pb_mrq", "ps_ttm", "pcf_ocf_ttm"}
        unknown = set(required_fields) - allowed
        if unknown:
            raise ValueError(f"unsupported required supplemental fields: {sorted(unknown)}")
        rows = self._query(
            "SELECT trade_date, pe_ttm, pb_mrq, ps_ttm, pcf_ocf_ttm, pit_status "
            "FROM qr_valuation_daily WHERE symbol = %s AND trade_date >= %s AND trade_date <= %s ORDER BY trade_date",
            (symbol, start_date, end_date),
        )
        if not rows:
            raise ValueError(f"no published valuation data for {symbol} between {start_date} and {end_date}")
        missing = [row for row in rows if any(row.get(field) is None for field in required_fields)]
        if missing:
            raise ValueError(f"required supplemental fields missing for {symbol}: {required_fields}")
        return {
            "rows": rows,
            "pit_status": "PARTIAL" if any(row.get("pit_status") != "PASS" for row in rows) else "PASS",
            "excluded_samples": sum(1 for row in rows if any(row.get(field) is None for field in allowed)),
        }

    def industry_as_of(self, symbol: str, as_of: str) -> dict[str, Any] | None:
        rows = self._query(
            "SELECT symbol, industry_code, effective_from, effective_to, pit_status "
            "FROM qr_sw_industry_history WHERE symbol = %s AND effective_from <= %s "
            "AND (effective_to IS NULL OR effective_to >= %s) ORDER BY effective_from DESC LIMIT 1",
            (symbol, as_of, as_of),
        )
        return rows[0] if rows else None

    def lifecycle_as_of(self, symbol: str, as_of: str) -> dict[str, Any] | None:
        rows = self._query(
            "SELECT symbol, list_date, delist_date, status, pit_status FROM qr_security_lifecycle "
            "WHERE symbol = %s AND list_date <= %s AND (delist_date IS NULL OR delist_date > %s)",
            (symbol, as_of, as_of),
        )
        return rows[0] if rows else None

    def _query(self, sql: str, args: tuple[Any, ...]) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, args)
                return list(cursor.fetchall())
        finally:
            close = getattr(connection, "close", None)
            if close is not None:
                close()
