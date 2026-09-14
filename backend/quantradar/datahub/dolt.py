"""The only writer for QuantRadar's supplemental Dolt database."""

from __future__ import annotations

from typing import Any, Iterable
from uuid import uuid4

from .v3_contracts import snapshot_revision_plan


_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS qr_valuation_daily (
      trade_date DATE NOT NULL,
      symbol VARCHAR(16) NOT NULL,
      pe_ttm DOUBLE NULL, pb_mrq DOUBLE NULL, ps_ttm DOUBLE NULL, pcf_ocf_ttm DOUBLE NULL,
      source VARCHAR(64) NOT NULL, raw_sha256 CHAR(64) NOT NULL, adapter_version VARCHAR(128) NOT NULL,
      fetched_at VARCHAR(40) NOT NULL, available_date DATE NULL, pit_status VARCHAR(16) NOT NULL,
      PRIMARY KEY (trade_date, symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_sw_industry_history (
      symbol VARCHAR(16) NOT NULL, industry_code VARCHAR(6) NOT NULL,
      effective_from DATE NOT NULL, effective_to DATE NULL,
      source VARCHAR(64) NOT NULL, raw_sha256 CHAR(64) NOT NULL, adapter_version VARCHAR(128) NOT NULL,
      fetched_at VARCHAR(40) NOT NULL, available_date DATE NULL, pit_status VARCHAR(16) NOT NULL,
      PRIMARY KEY (symbol, effective_from)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_security_lifecycle (
      symbol VARCHAR(16) NOT NULL, list_date DATE NOT NULL, delist_date DATE NULL, status VARCHAR(16) NOT NULL,
      source VARCHAR(64) NOT NULL, raw_sha256 CHAR(64) NOT NULL, adapter_version VARCHAR(128) NOT NULL,
      fetched_at VARCHAR(40) NOT NULL, available_date DATE NULL, pit_status VARCHAR(16) NOT NULL,
      PRIMARY KEY (symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_trade_status_daily (
      trade_date DATE NOT NULL, symbol VARCHAR(16) NOT NULL,
      tradestatus TINYINT NULL, is_st TINYINT NULL, turn DOUBLE NULL,
      source VARCHAR(64) NOT NULL, raw_sha256 CHAR(64) NOT NULL, adapter_version VARCHAR(128) NOT NULL,
      source_contract_id VARCHAR(64) NULL,
      fetched_at VARCHAR(40) NOT NULL, available_date DATE NULL, pit_status VARCHAR(16) NOT NULL,
      PRIMARY KEY (trade_date, symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_a_stock_eod_price (
      trade_date DATE NOT NULL, symbol VARCHAR(16) NOT NULL,
      open DOUBLE NOT NULL, high DOUBLE NOT NULL, low DOUBLE NOT NULL, close DOUBLE NOT NULL,
      volume DOUBLE NOT NULL, amount DOUBLE NOT NULL, preclose DOUBLE NULL,
      source VARCHAR(64) NOT NULL, raw_sha256 CHAR(64) NOT NULL, adapter_version VARCHAR(128) NOT NULL,
      source_contract_id VARCHAR(64) NOT NULL, unit_contract_version VARCHAR(64) NOT NULL,
      fetched_at VARCHAR(40) NOT NULL, available_date DATE NULL, pit_status VARCHAR(16) NOT NULL,
      PRIMARY KEY (trade_date, symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_market_cap_daily (
      trade_date DATE NOT NULL, symbol VARCHAR(16) NOT NULL,
      total_market_cap_cny DOUBLE NOT NULL,
      source VARCHAR(64) NOT NULL, raw_sha256 CHAR(64) NOT NULL, adapter_version VARCHAR(128) NOT NULL,
      fetched_at VARCHAR(40) NOT NULL, available_date DATE NULL, pit_status VARCHAR(16) NOT NULL,
      qualification VARCHAR(64) NOT NULL,
      PRIMARY KEY (trade_date, symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_etf_eod_price (
      trade_date DATE NOT NULL, symbol VARCHAR(16) NOT NULL,
      open DOUBLE NOT NULL, high DOUBLE NOT NULL, low DOUBLE NOT NULL, close DOUBLE NOT NULL,
      volume_shares DOUBLE NOT NULL, amount_cny DOUBLE NOT NULL,
      source VARCHAR(64) NOT NULL, raw_sha256 CHAR(64) NOT NULL, adapter_version VARCHAR(128) NOT NULL,
      fetched_at VARCHAR(40) NOT NULL, available_at DATE NULL, pit_status VARCHAR(16) NOT NULL,
      adjustment VARCHAR(16) NOT NULL, unit_status VARCHAR(64) NOT NULL,
      PRIMARY KEY (trade_date, symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_etf_event_announcement (
      symbol VARCHAR(16) NOT NULL, report_id VARCHAR(64) NOT NULL,
      fund_code VARCHAR(6) NOT NULL, title VARCHAR(512) NOT NULL, publish_date DATE NOT NULL,
      source VARCHAR(64) NOT NULL, raw_sha256 CHAR(64) NOT NULL, adapter_version VARCHAR(128) NOT NULL,
      fetched_at VARCHAR(40) NOT NULL, available_at DATE NOT NULL, qualification VARCHAR(64) NOT NULL,
      PRIMARY KEY (symbol, report_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_etf_master (
      symbol VARCHAR(16) NOT NULL, fund_code VARCHAR(6) NOT NULL, fund_name VARCHAR(256) NULL,
      exchange VARCHAR(8) NOT NULL, listing_date DATE NOT NULL, termination_date DATE NULL,
      fund_established_date DATE NULL, tracking_index VARCHAR(256) NULL, fund_type VARCHAR(128) NULL,
      currency VARCHAR(8) NULL, source VARCHAR(64) NOT NULL, raw_sha256 CHAR(64) NOT NULL,
      adapter_version VARCHAR(128) NOT NULL, fetched_at VARCHAR(40) NOT NULL,
      qualification VARCHAR(64) NOT NULL, listing_date_status VARCHAR(96) NOT NULL,
      PRIMARY KEY (symbol)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_etf_corporate_action (
      symbol VARCHAR(16) NOT NULL, ex_date DATE NOT NULL, event_kind VARCHAR(32) NOT NULL,
      cash_per_unit DOUBLE NULL, record_date DATE NULL, pay_date DATE NULL, share_multiplier DOUBLE NULL,
      source VARCHAR(64) NOT NULL, raw_sha256 CHAR(64) NOT NULL, adapter_version VARCHAR(128) NOT NULL,
      fetched_at VARCHAR(40) NOT NULL, available_at DATE NOT NULL, qualification VARCHAR(64) NOT NULL,
      coverage VARCHAR(64) NOT NULL, PRIMARY KEY (symbol, ex_date, event_kind)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_etf_trading_rule (
      symbol VARCHAR(16) NOT NULL, effective_from DATE NOT NULL, effective_to DATE NULL,
      exchange VARCHAR(8) NOT NULL, lot_size INT NULL, tick_size DOUBLE NULL, limit_pct DOUBLE NULL,
      turnover_status VARCHAR(64) NOT NULL, fee_status VARCHAR(64) NOT NULL, special_status VARCHAR(64) NOT NULL,
      rule_scope VARCHAR(64) NOT NULL, source VARCHAR(64) NOT NULL, raw_sha256 CHAR(64) NOT NULL,
      adapter_version VARCHAR(128) NOT NULL, fetched_at VARCHAR(40) NOT NULL, available_at DATE NOT NULL,
      qualification VARCHAR(64) NOT NULL, PRIMARY KEY (symbol, effective_from)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_index_snapshot_version (
      snapshot_id VARCHAR(64) NOT NULL, dataset_type VARCHAR(48) NOT NULL, index_code VARCHAR(16) NOT NULL,
      source_date DATE NULL, observed_at VARCHAR(40) NOT NULL,
      content_hash CHAR(64) NOT NULL, raw_sha256 CHAR(64) NOT NULL,
      source VARCHAR(96) NOT NULL, adapter_version VARCHAR(128) NOT NULL,
      revision_no INT NOT NULL, supersedes_snapshot_id VARCHAR(64) NULL,
      effective_date DATE NULL, effective_semantics VARCHAR(96) NOT NULL,
      effective_evidence_ref VARCHAR(256) NULL, qualification VARCHAR(64) NOT NULL, pit_status VARCHAR(16) NOT NULL,
      PRIMARY KEY (snapshot_id), UNIQUE KEY qr_index_snapshot_revision (dataset_type, index_code, source_date, revision_no)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_index_constituent_snapshot (
      snapshot_id VARCHAR(64) NOT NULL, security_code VARCHAR(16) NOT NULL,
      security_name VARCHAR(256) NULL, exchange VARCHAR(16) NULL,
      PRIMARY KEY (snapshot_id, security_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_index_weight_snapshot (
      snapshot_id VARCHAR(64) NOT NULL, security_code VARCHAR(16) NOT NULL,
      weight_raw DOUBLE NULL, weight_unit VARCHAR(32) NOT NULL, weight_fraction DOUBLE NULL,
      PRIMARY KEY (snapshot_id, security_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_sw_index_component_snapshot (
      snapshot_id VARCHAR(64) NOT NULL, security_code VARCHAR(16) NOT NULL,
      security_name VARCHAR(256) NULL, weight_raw DOUBLE NULL,
      member_effective_date DATE NULL, member_effective_semantics VARCHAR(96) NOT NULL,
      member_effective_evidence VARCHAR(256) NULL,
      PRIMARY KEY (snapshot_id, security_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_stock_statement_version (
      statement_version_id VARCHAR(64) NOT NULL, symbol VARCHAR(16) NOT NULL,
      statement_type VARCHAR(24) NOT NULL, report_period DATE NOT NULL,
      report_type VARCHAR(64) NULL, statement_scope VARCHAR(24) NOT NULL, period_type VARCHAR(24) NOT NULL,
      source_announcement_date DATE NULL, announcement_precision VARCHAR(24) NOT NULL,
      source_fetch_at VARCHAR(40) NOT NULL, currency VARCHAR(16) NULL,
      source VARCHAR(96) NOT NULL, raw_sha256 CHAR(64) NOT NULL, adapter_version VARCHAR(128) NOT NULL,
      pit_status VARCHAR(16) NOT NULL, qualification VARCHAR(64) NOT NULL, raw_payload_json LONGTEXT NOT NULL,
      PRIMARY KEY (statement_version_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_stock_balance_sheet (
      statement_version_id VARCHAR(64) NOT NULL, mapping_version VARCHAR(64) NOT NULL,
      conservative_available_at VARCHAR(40) NULL, availability_rule_version VARCHAR(96) NULL,
      total_assets DOUBLE NULL, total_liabilities DOUBLE NULL, total_equity DOUBLE NULL, cash DOUBLE NULL,
      accounts_receivable DOUBLE NULL, inventory DOUBLE NULL, short_term_debt DOUBLE NULL, long_term_debt DOUBLE NULL,
      PRIMARY KEY (statement_version_id, mapping_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_stock_income_statement (
      statement_version_id VARCHAR(64) NOT NULL, mapping_version VARCHAR(64) NOT NULL,
      conservative_available_at VARCHAR(40) NULL, availability_rule_version VARCHAR(96) NULL,
      operating_revenue DOUBLE NULL, operating_profit DOUBLE NULL, total_profit DOUBLE NULL,
      net_profit DOUBLE NULL, net_profit_parent DOUBLE NULL,
      PRIMARY KEY (statement_version_id, mapping_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_stock_cashflow_statement (
      statement_version_id VARCHAR(64) NOT NULL, mapping_version VARCHAR(64) NOT NULL,
      conservative_available_at VARCHAR(40) NULL, availability_rule_version VARCHAR(96) NULL,
      operating_cash_flow DOUBLE NULL, investing_cash_flow DOUBLE NULL, financing_cash_flow DOUBLE NULL,
      cash_change DOUBLE NULL, capex DOUBLE NULL,
      PRIMARY KEY (statement_version_id, mapping_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qr_stock_earnings_report (
      symbol VARCHAR(16) NOT NULL, report_period DATE NOT NULL, observed_at VARCHAR(40) NOT NULL,
      latest_announcement_date DATE NULL, source VARCHAR(96) NOT NULL, raw_sha256 CHAR(64) NOT NULL,
      adapter_version VARCHAR(128) NOT NULL, qualification VARCHAR(64) NOT NULL,
      PRIMARY KEY (symbol, report_period, observed_at)
    )
    """,
)


class SupplementalStore:
    """Upsert staged normalized values; publication is handled by ReleaseStore afterwards."""

    def __init__(self, connection: Any, progress=None) -> None:
        self.connection = connection
        self.progress = progress

    def ensure_schema(self) -> None:
        with self.connection.cursor() as cursor:
            for statement in _SCHEMA:
                cursor.execute(statement)
            cursor.execute("SHOW COLUMNS FROM qr_trade_status_daily")
            fetchall = getattr(cursor, "fetchall", None)
            columns = {str(row["Field"]) for row in fetchall()} if fetchall is not None else {"source_contract_id"}
            if "source_contract_id" not in columns:
                cursor.execute("ALTER TABLE qr_trade_status_daily ADD COLUMN source_contract_id VARCHAR(64) NULL AFTER adapter_version")
                cursor.execute("UPDATE qr_trade_status_daily SET source_contract_id='baostock-daily-v2' WHERE source='baostock' AND source_contract_id IS NULL")
        self.connection.commit()

    def prepare_canonical_valuation(self) -> None:
        """Remove the frozen BaoStock validation rows before adopting OCF semantics.

        The prior rows used a differently-defined NCF field.  They remain readable
        through their already-published Dolt commit, but may never coexist in the
        new canonical table.
        """
        with self.connection.cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM qr_valuation_daily")
            columns = {str(row["Field"]) for row in cursor.fetchall()}
            if "pcf_ncf_ttm" in columns:
                cursor.execute("DELETE FROM qr_valuation_daily")
                cursor.execute("ALTER TABLE qr_valuation_daily DROP COLUMN pcf_ncf_ttm")
                cursor.execute("ALTER TABLE qr_valuation_daily ADD COLUMN pcf_ocf_ttm DOUBLE NULL AFTER ps_ttm")
        self.connection.commit()

    def upsert_valuations(self, rows: Iterable[dict[str, Any]]) -> None:
        self._upsert(
            "qr_valuation_daily",
            ("trade_date", "symbol", "pe_ttm", "pb_mrq", "ps_ttm", "pcf_ocf_ttm", *self._PROVENANCE),
            rows,
        )

    def upsert_industries(self, rows: Iterable[dict[str, Any]]) -> None:
        self._upsert(
            "qr_sw_industry_history",
            ("symbol", "industry_code", "effective_from", "effective_to", *self._PROVENANCE),
            rows,
        )

    def upsert_lifecycles(self, rows: Iterable[dict[str, Any]]) -> None:
        self._upsert(
            "qr_security_lifecycle",
            ("symbol", "list_date", "delist_date", "status", *self._PROVENANCE),
            rows,
        )

    def upsert_trade_status(self, rows: Iterable[dict[str, Any]]) -> None:
        self._upsert(
            "qr_trade_status_daily",
            ("trade_date", "symbol", "tradestatus", "is_st", "turn", *self._PROVENANCE, "source_contract_id"),
            rows,
        )

    def upsert_prices(self, rows: Iterable[dict[str, Any]]) -> None:
        self._upsert(
            "qr_a_stock_eod_price",
            ("trade_date", "symbol", "open", "high", "low", "close", "volume", "amount", "preclose",
             *self._PROVENANCE, "source_contract_id", "unit_contract_version"),
            rows,
        )

    def upsert_market_caps(self, rows: Iterable[dict[str, Any]]) -> None:
        self._upsert(
            "qr_market_cap_daily",
            ("trade_date", "symbol", "total_market_cap_cny", *self._PROVENANCE, "qualification"),
            rows,
        )

    def upsert_etf_prices(self, rows: Iterable[dict[str, Any]]) -> None:
        self._upsert(
            "qr_etf_eod_price",
            ("trade_date", "symbol", "open", "high", "low", "close", "volume_shares", "amount_cny",
             "source", "raw_sha256", "adapter_version", "fetched_at", "available_at", "pit_status",
             "adjustment", "unit_status"),
            rows,
        )

    def upsert_etf_announcements(self, rows: Iterable[dict[str, Any]]) -> None:
        self._upsert(
            "qr_etf_event_announcement",
            ("symbol", "report_id", "fund_code", "title", "publish_date", "source", "raw_sha256",
             "adapter_version", "fetched_at", "available_at", "qualification"),
            rows,
        )

    def upsert_etf_master(self, rows: Iterable[dict[str, Any]]) -> None:
        self._upsert("qr_etf_master", ("symbol", "fund_code", "fund_name", "exchange", "listing_date",
            "termination_date", "fund_established_date", "tracking_index", "fund_type", "currency", "source",
            "raw_sha256", "adapter_version", "fetched_at", "qualification", "listing_date_status"), rows)

    def upsert_etf_corporate_actions(self, rows: Iterable[dict[str, Any]]) -> None:
        self._upsert("qr_etf_corporate_action", ("symbol", "ex_date", "event_kind", "cash_per_unit", "record_date",
            "pay_date", "share_multiplier", "source", "raw_sha256", "adapter_version", "fetched_at", "available_at",
            "qualification", "coverage"), rows)

    def upsert_etf_trading_rules(self, rows: Iterable[dict[str, Any]]) -> None:
        self._upsert("qr_etf_trading_rule", ("symbol", "effective_from", "effective_to", "exchange", "lot_size",
            "tick_size", "limit_pct", "turnover_status", "fee_status", "special_status", "rule_scope", "source",
            "raw_sha256", "adapter_version", "fetched_at", "available_at", "qualification"), rows)

    def write_index_snapshot(self, *, version: dict[str, Any], constituents: list[dict[str, Any]],
                             weights: list[dict[str, Any]], sw_components: list[dict[str, Any]]) -> dict[str, Any]:
        """Append an immutable source revision, or retain an identical receipt."""
        required = ("dataset_type", "index_code", "observed_at", "content_hash", "raw_sha256", "source", "adapter_version", "effective_semantics", "qualification", "pit_status")
        missing = [key for key in required if not version.get(key)]
        if missing:
            raise ValueError(f"snapshot version missing fields: {missing}")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT snapshot_id, content_hash, revision_no FROM qr_index_snapshot_version "
                           "WHERE dataset_type=%s AND index_code=%s AND source_date <=> %s ORDER BY revision_no DESC LIMIT 1",
                           (version["dataset_type"], version["index_code"], version.get("source_date")))
            plan = snapshot_revision_plan(cursor.fetchone(), str(version["content_hash"]))
            if plan["action"] == "NO_CHANGE":
                return {**plan, "snapshot_id": None}
            snapshot_id = str(uuid4())
            fields = ("snapshot_id", "dataset_type", "index_code", "source_date", "observed_at", "content_hash", "raw_sha256", "source", "adapter_version", "revision_no", "supersedes_snapshot_id", "effective_date", "effective_semantics", "effective_evidence_ref", "qualification", "pit_status")
            values = {**version, "snapshot_id": snapshot_id, **plan}
            cursor.execute(f"INSERT INTO qr_index_snapshot_version ({', '.join(fields)}) VALUES ({', '.join(['%s'] * len(fields))})",
                           tuple(values.get(field) for field in fields))
            self._insert_snapshot_members(cursor, "qr_index_constituent_snapshot", ("snapshot_id", "security_code", "security_name", "exchange"), snapshot_id, constituents)
            self._insert_snapshot_members(cursor, "qr_index_weight_snapshot", ("snapshot_id", "security_code", "weight_raw", "weight_unit", "weight_fraction"), snapshot_id, weights)
            self._insert_snapshot_members(cursor, "qr_sw_index_component_snapshot", ("snapshot_id", "security_code", "security_name", "weight_raw", "member_effective_date", "member_effective_semantics", "member_effective_evidence"), snapshot_id, sw_components)
        self.connection.commit()
        return {**plan, "snapshot_id": snapshot_id}

    @staticmethod
    def _insert_snapshot_members(cursor: Any, table: str, fields: tuple[str, ...], snapshot_id: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        if any(not row.get("security_code") for row in rows):
            raise ValueError(f"{table} has a member without security_code")
        sql = f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({', '.join(['%s'] * len(fields))})"
        values = [tuple(snapshot_id if field == "snapshot_id" else row.get(field) for field in fields) for row in rows]
        SupplementalStore._write_batch(cursor, sql, values)

    _PROVENANCE = ("source", "raw_sha256", "adapter_version", "fetched_at", "available_date", "pit_status")

    def _upsert(self, table: str, fields: tuple[str, ...], rows: Iterable[dict[str, Any]]) -> None:
        placeholders = ", ".join(["%s"] * len(fields))
        columns = ", ".join(fields)
        update_fields = [field for field in fields if field not in self._key_fields(table)]
        if table == 'qr_valuation_daily':
            economic = ('pe_ttm', 'pb_mrq', 'ps_ttm', 'pcf_ocf_ttm')
            changed = 'NOT (' + ' AND '.join(f'{f} <=> VALUES({f})' for f in economic) + ')'
            # MySQL assignments run left to right: preserve provenance for equal
            # values before assigning the economic fields.
            updates = ', '.join([f'{f}=IF({changed}, VALUES({f}), {f})' for f in self._PROVENANCE]
                                + [f'{f}=VALUES({f})' for f in economic])
        else:
            updates = ", ".join(f"{field}=VALUES({field})" for field in update_fields)
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}"
        wrote = False
        processed = 0
        with self.connection.cursor() as cursor:
            batch: list[tuple[Any, ...]] = []
            for row in rows:
                batch.append(tuple(row.get(field) for field in fields))
                wrote = True
                if len(batch) == 5_000:
                    self._write_batch(cursor, sql, batch)
                    processed += len(batch)
                    if self.progress and processed % 100_000 == 0:
                        self.progress(table, processed)
                    batch.clear()
            if batch:
                self._write_batch(cursor, sql, batch)
        if not wrote:
            return
        self.connection.commit()

    @staticmethod
    def _write_batch(cursor: Any, sql: str, values: list[tuple[Any, ...]]) -> None:
        executemany = getattr(cursor, "executemany", None)
        if executemany is not None:
            executemany(sql, values)
            return
        for value in values:  # lightweight test doubles intentionally expose execute only
            cursor.execute(sql, value)

    @staticmethod
    def _key_fields(table: str) -> set[str]:
        return {
            "qr_valuation_daily": {"trade_date", "symbol"},
            "qr_sw_industry_history": {"symbol", "effective_from"},
            "qr_security_lifecycle": {"symbol"},
            "qr_trade_status_daily": {"trade_date", "symbol"},
            "qr_a_stock_eod_price": {"trade_date", "symbol"},
            "qr_market_cap_daily": {"trade_date", "symbol"},
            "qr_etf_eod_price": {"trade_date", "symbol"},
            "qr_etf_event_announcement": {"symbol", "report_id"},
            "qr_etf_master": {"symbol"},
            "qr_etf_corporate_action": {"symbol", "ex_date", "event_kind"},
            "qr_etf_trading_rule": {"symbol", "effective_from"},
        }[table]

    def commit(self, message: str) -> str:
        if not str(message).strip():
            raise ValueError("Dolt commit message is required")
        self._previous_commit = self._head_commit()
        with self.connection.cursor() as cursor:
            cursor.execute("CALL DOLT_COMMIT('-Am', %s)", (message,))
            cursor.execute("SELECT DOLT_HASHOF('HEAD') AS commit_hash")
            row = cursor.fetchone()
        self.connection.commit()
        if not row or not row.get("commit_hash"):
            raise RuntimeError("supplemental Dolt did not return a commit hash")
        return str(row["commit_hash"])

    def _head_commit(self) -> str | None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT DOLT_HASHOF('HEAD') AS commit_hash")
            row = cursor.fetchone()
        return str(row["commit_hash"]) if row and row.get("commit_hash") else None

    def revision_counts(self, commit: str) -> dict[str, int]:
        """Count changed existing records between the last two supplemental commits."""
        prior = getattr(self, "_previous_commit", None)
        if not prior or prior == commit:
            return {"valuation_daily": 0, "sw_industry_history": 0, "security_lifecycle": 0}
        tables = {
            "valuation_daily": "qr_valuation_daily",
            "sw_industry_history": "qr_sw_industry_history",
            "security_lifecycle": "qr_security_lifecycle",
        }
        with self.connection.cursor() as cursor:
            result = {}
            for name, table in tables.items():
                cursor.execute(
                    f"SELECT COUNT(*) AS changes FROM dolt_diff_{table} "
                    "WHERE from_commit=%s AND to_commit=%s AND diff_type='modified'", (prior, commit)
                )
                result[name] = int((cursor.fetchone() or {}).get("changes") or 0)
        return result
