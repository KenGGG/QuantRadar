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

    def lifecycles(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """Return fixed-release lifecycle facts for an explicit research pool."""
        if not symbols:
            return {}
        marks = ",".join(["%s"] * len(symbols))
        rows = self._query(
            "SELECT symbol, list_date, delist_date, status, pit_status FROM qr_security_lifecycle "
            f"WHERE symbol IN ({marks})", tuple(symbols),
        )
        return {row["symbol"]: row for row in rows}

    def trade_status(self, symbols: list[str], start_date: str | None, end_date: str | None, count: int | None) -> dict[str, list[dict[str, Any]]]:
        if not symbols:
            return {}
        marks = ",".join(["%s"] * len(symbols))
        where, values = [f"symbol IN ({marks})"], list(symbols)
        if start_date:
            where.append("trade_date >= %s"); values.append(start_date)
        if end_date:
            where.append("trade_date <= %s"); values.append(end_date)
        rows = self._query("SELECT symbol, trade_date, tradestatus, is_st, turn FROM qr_trade_status_daily WHERE " + " AND ".join(where) + " ORDER BY symbol, trade_date", tuple(values))
        grouped = {symbol: [] for symbol in symbols}
        for row in rows:
            grouped.setdefault(row["symbol"], []).append(row)
        if count is not None:
            for symbol in grouped:
                grouped[symbol] = grouped[symbol][-int(count):]
        return grouped

    def prices(self, symbols: list[str], start_date: str | None, end_date: str | None) -> dict[str, list[dict[str, Any]]]:
        """Return raw, release-pinned price patches; Provider applies count semantics."""
        if not symbols:
            return {}
        marks = ",".join(["%s"] * len(symbols))
        where, values = [f"symbol IN ({marks})"], list(symbols)
        if start_date:
            where.append("trade_date >= %s"); values.append(start_date)
        if end_date:
            where.append("trade_date <= %s"); values.append(end_date)
        rows = self._query(
            "SELECT symbol, trade_date, open, high, low, close, volume, amount, preclose, unit_contract_version "
            "FROM qr_a_stock_eod_price WHERE " + " AND ".join(where) + " ORDER BY symbol, trade_date",
            tuple(values),
        )
        grouped = {symbol: [] for symbol in symbols}
        for row in rows:
            grouped.setdefault(row["symbol"], []).append(row)
        return grouped

    def market_cap(self, symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
        """Read total market cap solely from the release-pinned candidate table."""
        rows = self._query(
            "SELECT trade_date, total_market_cap_cny, pit_status FROM qr_market_cap_daily "
            "WHERE symbol = %s AND trade_date >= %s AND trade_date <= %s ORDER BY trade_date",
            (symbol, start_date, end_date),
        )
        if not rows:
            raise ValueError(f"no published total market cap for {symbol} between {start_date} and {end_date}")
        return {
            'rows': rows,
            'pit_status': 'PARTIAL' if any(row.get('pit_status') != 'PASS' for row in rows) else 'PASS',
        }

    def market_caps(self, symbols: list[str], start_date: str, end_date: str) -> dict[str, list[dict[str, Any]]]:
        """Read a release-pinned total-market-cap panel without filling gaps."""
        if not symbols:
            return {}
        marks = ','.join(['%s'] * len(symbols))
        rows = self._query(
            'SELECT symbol, trade_date, total_market_cap_cny, pit_status FROM qr_market_cap_daily '
            f'WHERE symbol IN ({marks}) AND trade_date >= %s AND trade_date <= %s ORDER BY symbol, trade_date',
            (*symbols, start_date, end_date),
        )
        grouped = {symbol: [] for symbol in symbols}
        for row in rows:
            grouped.setdefault(row['symbol'], []).append(row)
        return grouped

    def etf_prices(self, symbols: list[str], start_date: str | None, end_date: str | None) -> dict[str, list[dict[str, Any]]]:
        """Read unadjusted ETF prices only from the release-pinned supplement."""
        if not symbols:
            return {}
        marks = ','.join(['%s'] * len(symbols))
        where, values = [f'symbol IN ({marks})'], list(symbols)
        if start_date:
            where.append('trade_date >= %s'); values.append(start_date)
        if end_date:
            where.append('trade_date <= %s'); values.append(end_date)
        rows = self._query(
            'SELECT symbol, trade_date, open, high, low, close, volume_shares, amount_cny, pit_status '
            f'FROM qr_etf_eod_price WHERE {" AND ".join(where)} ORDER BY symbol, trade_date',
            tuple(values),
        )
        grouped = {symbol: [] for symbol in symbols}
        for row in rows:
            grouped.setdefault(row['symbol'], []).append(row)
        return grouped

    def etf_announcements(self, symbols: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not symbols:
            return {}
        marks = ','.join(['%s'] * len(symbols))
        rows = self._query(
            'SELECT symbol, report_id, publish_date, title, qualification FROM qr_etf_event_announcement '
            f'WHERE symbol IN ({marks}) ORDER BY symbol, publish_date, report_id', tuple(symbols),
        )
        grouped = {symbol: [] for symbol in symbols}
        for row in rows:
            grouped.setdefault(row['symbol'], []).append(row)
        return grouped

    def etf_master(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        if not symbols:
            return {}
        marks = ','.join(['%s'] * len(symbols))
        rows = self._query(
            'SELECT symbol, fund_code, fund_name, exchange, listing_date, termination_date, '
            'fund_established_date, tracking_index, fund_type, currency, qualification, listing_date_status '
            f'FROM qr_etf_master WHERE symbol IN ({marks}) ORDER BY symbol', tuple(symbols),
        )
        return {row['symbol']: row for row in rows}

    def etf_corporate_actions(self, symbols: list[str], start_date: str, end_date: str, *, as_of: str) -> dict[str, list[dict[str, Any]]]:
        """Read only action terms published by ``as_of`` from the pinned release."""
        if not symbols:
            return {}
        marks = ','.join(['%s'] * len(symbols))
        rows = self._query(
            'SELECT symbol, ex_date, event_kind, cash_per_unit, record_date, pay_date, share_multiplier, '
            'available_at, qualification, coverage FROM qr_etf_corporate_action '
            f'WHERE symbol IN ({marks}) AND ex_date >= %s AND ex_date <= %s AND available_at <= %s '
            'ORDER BY symbol, ex_date, event_kind',
            (*symbols, start_date, end_date, as_of),
        )
        grouped = {symbol: [] for symbol in symbols}
        for row in rows:
            grouped.setdefault(row['symbol'], []).append(row)
        return grouped

    def etf_trading_rules(self, symbols: list[str], *, as_of: str) -> dict[str, dict[str, Any]]:
        """Return the release-pinned rule version effective on the requested day."""
        if not symbols:
            return {}
        marks = ','.join(['%s'] * len(symbols))
        rows = self._query(
            'SELECT symbol, effective_from, effective_to, exchange, lot_size, tick_size, limit_pct, '
            'turnover_status, fee_status, special_status, qualification FROM qr_etf_trading_rule '
            f'WHERE symbol IN ({marks}) AND effective_from <= %s AND (effective_to IS NULL OR effective_to >= %s) '
            'ORDER BY symbol, effective_from DESC',
            (*symbols, as_of, as_of),
        )
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            result.setdefault(row['symbol'], row)
        return result

    def get_index_snapshot(self, index_code: str, *, as_of: str | None = None,
                           observed_before: str | None = None, strict_pit: bool = False,
                           dataset_type: str | None = None) -> dict[str, Any] | None:
        """Read one V3 snapshot explicitly; legacy index APIs keep their semantics."""
        from .v3_contracts import snapshot_eligibility
        where, args = ["index_code=%s"], [index_code]
        if dataset_type:
            where.append("dataset_type=%s"); args.append(dataset_type)
        if observed_before:
            cutoff = observed_before + "T23:59:59.999999+08:00" if len(observed_before) == 10 else observed_before
            where.append("observed_at <= %s"); args.append(cutoff)
        # A source date is the market-date constraint. NULL is intentionally
        # excluded for as_of requests even in non-strict mode.
        if as_of:
            where.append("source_date IS NOT NULL AND source_date <= %s"); args.append(as_of)
        rows = self._query("SELECT * FROM qr_index_snapshot_version WHERE " + " AND ".join(where) +
                           " ORDER BY source_date DESC, observed_at DESC, revision_no DESC", tuple(args))
        for row in rows:
            eligibility = snapshot_eligibility(row, as_of=as_of, observed_before=observed_before, strict_pit=strict_pit)
            if not eligibility["eligible"]:
                continue
            members = self._snapshot_members(str(row["snapshot_id"]), str(row["dataset_type"]))
            return {**row, "members": members, "pit_reason": eligibility["reason"]}
        return None

    def get_index_weight_snapshot(self, index_code: str, *, as_of: str | None = None,
                                  observed_before: str | None = None, strict_pit: bool = False) -> dict[str, Any] | None:
        """Return only a V3 weight snapshot, without changing legacy weights."""
        return self.get_index_snapshot(index_code, as_of=as_of, observed_before=observed_before,
                                       strict_pit=strict_pit, dataset_type="CSI_WEIGHTS")

    def financial_statement(self, symbol: str, statement_type: str, *, as_of: str,
                            mapping_version: str | None = None,
                            observed_before: str | None = None,
                            strict_pit: bool = False) -> list[dict[str, Any]]:
        """Read one explicit mapping contract from this release.

        ``as_of`` is the business-date availability boundary.  ``observed_before``
        constrains what had been received locally; strict PIT requires it and only
        admits records whose source qualification is PASS.
        """
        table = {"balance": "qr_stock_balance_sheet", "income": "qr_stock_income_statement", "cashflow": "qr_stock_cashflow_statement"}.get(statement_type)
        if table is None:
            raise ValueError("unsupported statement_type")
        if not mapping_version:
            raise ValueError("financial_statement requires an explicit mapping_version")
        if strict_pit and not observed_before:
            raise ValueError("strict_pit financial_statement requires observed_before")
        where = ["v.symbol=%s", "m.mapping_version=%s", "m.conservative_available_at IS NOT NULL", "m.conservative_available_at<=%s"]
        args: list[Any] = [symbol, mapping_version, as_of]
        if observed_before:
            cutoff = observed_before + "T23:59:59.999999+08:00" if len(observed_before) == 10 else observed_before
            where.append("v.source_fetch_at<=%s"); args.append(cutoff)
        if strict_pit:
            where.append("v.pit_status='PASS'")
        return self._query(
            "SELECT v.symbol,v.report_period,v.source_announcement_date,v.pit_status,m.* "
            f"FROM qr_stock_statement_version v JOIN {table} m ON v.statement_version_id=m.statement_version_id "
            "WHERE " + " AND ".join(where) + " ORDER BY v.report_period, v.statement_version_id", tuple(args),
        )

    def _snapshot_members(self, snapshot_id: str, dataset_type: str) -> list[dict[str, Any]]:
        table = "qr_index_weight_snapshot" if dataset_type == "CSI_WEIGHTS" else (
            "qr_sw_index_component_snapshot" if dataset_type == "SW_COMPONENTS" else "qr_index_constituent_snapshot"
        )
        return self._query(f"SELECT * FROM {table} WHERE snapshot_id=%s ORDER BY security_code", (snapshot_id,))

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
