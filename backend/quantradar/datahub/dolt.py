"""The only writer for QuantRadar's supplemental Dolt database."""

from __future__ import annotations

from typing import Any, Iterable


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
)


class SupplementalStore:
    """Upsert staged normalized values; publication is handled by ReleaseStore afterwards."""

    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def ensure_schema(self) -> None:
        with self.connection.cursor() as cursor:
            for statement in _SCHEMA:
                cursor.execute(statement)
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

    _PROVENANCE = ("source", "raw_sha256", "adapter_version", "fetched_at", "available_date", "pit_status")

    def _upsert(self, table: str, fields: tuple[str, ...], rows: Iterable[dict[str, Any]]) -> None:
        placeholders = ", ".join(["%s"] * len(fields))
        columns = ", ".join(fields)
        update_fields = [field for field in fields if field not in self._key_fields(table)]
        updates = ", ".join(f"{field}=VALUES({field})" for field in update_fields)
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE {updates}"
        wrote = False
        with self.connection.cursor() as cursor:
            batch: list[tuple[Any, ...]] = []
            for row in rows:
                batch.append(tuple(row.get(field) for field in fields))
                wrote = True
                if len(batch) == 1_000:
                    self._write_batch(cursor, sql, batch)
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
        }[table]

    def commit(self, message: str) -> str:
        if not str(message).strip():
            raise ValueError("Dolt commit message is required")
        self._previous_commit = self._head_commit()
        with self.connection.cursor() as cursor:
            cursor.execute("CALL DOLT_COMMIT('-Am', %s)", (message,))
            cursor.execute("SELECT commit_hash FROM dolt_log ORDER BY date DESC LIMIT 1")
            row = cursor.fetchone()
        self.connection.commit()
        if not row or not row.get("commit_hash"):
            raise RuntimeError("supplemental Dolt did not return a commit hash")
        return str(row["commit_hash"])

    def _head_commit(self) -> str | None:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT commit_hash FROM dolt_log ORDER BY date DESC LIMIT 1")
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
