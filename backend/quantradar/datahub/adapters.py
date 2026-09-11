"""Pinned-source DataHub V1 adapters.

These adapters intentionally do not import ``a-stock-data`` at runtime.  They
implement only the three reviewed public-source paths and identify the pinned
reference implementation in every normalized row.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Iterable
import hashlib
import json
import socket

import pandas as pd
import requests

from .governor import RequestGovernor
from .sources import build_sw_level_one_intervals, normalize_baostock_daily_bundle, normalize_eastmoney_valuation_rows, normalize_lifecycle_row, normalize_valuation_rows


ASTOCK_DATA_COMMIT = "2012ce7cd0e75d379c5e6cbd3115514f300f3bc8"
ADAPTER_VERSION = f"a-stock-data@{ASTOCK_DATA_COMMIT}"
SW_URL = "https://www.swsresearch.com/swindex/pdf/SwClass2021/StockClassifyUse_stock.xls"
_BAOSTOCK_SESSION_SECONDS = 30
_BAOSTOCK_MAX_ROWS = 20_000
EASTMONEY_VALUE_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EASTMONEY_ADAPTER_VERSION = "eastmoney-date-slice-v1"


@dataclass(frozen=True)
class FetchedRows:
    dataset: str
    raw_bytes: bytes
    rows: list[dict[str, Any]]
    source: str
    fetched_at: str


class SourceResponseError(RuntimeError):
    """A rejected source response whose bytes still need durable audit storage."""

    def __init__(self, message: str, raw_bytes: bytes) -> None:
        super().__init__(message)
        self.raw_bytes = raw_bytes


class _EofFailingSocket:
    """Make the upstream SDK treat TCP EOF as an error instead of a busy loop."""

    def __init__(self, wrapped: Any) -> None:
        self._wrapped = wrapped

    def recv(self, size: int) -> bytes:
        value = self._wrapped.recv(size)
        if not value:
            raise ConnectionError("baostock connection closed before a complete response")
        return value

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


def _fetched_at() -> str:
    return datetime.now(timezone.utc).isoformat()


class EastmoneyValuationAdapter:
    """Date-sliced whole-market valuation adapter with explicit pagination."""

    source = "eastmoney:RPT_VALUEANALYSIS_DET"

    def __init__(self, *, governor: RequestGovernor, session: Any | None = None, page_size: int = 10_000) -> None:
        self.governor = governor
        self.session = session or requests.Session()
        self.page_size = max(1, min(int(page_size), 10_000))

    def _page(self, trade_date: str, page: int) -> tuple[dict[str, Any], bytes]:
        params = {
            "sortColumns": "SECURITY_CODE", "sortTypes": "1", "pageSize": str(self.page_size), "pageNumber": str(page),
            "reportName": "RPT_VALUEANALYSIS_DET", "columns": "ALL", "quoteColumns": "", "source": "WEB", "client": "WEB",
            "filter": f"(TRADE_DATE='{trade_date}')",
        }
        def request() -> tuple[dict[str, Any], bytes]:
            response = self.session.get(
                EASTMONEY_VALUE_URL, params=params, headers={"User-Agent": "QuantRadar DataHub/1"}, timeout=60
            )
            response.raise_for_status()
            payload = response.json()
            raw = getattr(response, "content", None) or json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            result = payload.get("result")
            if not isinstance(result, dict) or not result.get("data"):
                raise SourceResponseError(f"schema invalid Eastmoney empty result for {trade_date} page {page}", raw)
            return payload, raw

        return self.governor.call(f"valuation_daily/{trade_date}/page/{page}", request)

    def valuation_date(self, trade_date: str) -> FetchedRows:
        first, first_raw = self._page(trade_date, 1)
        result = first.get("result") or {}
        total = int(result.get("total") or 0)
        reported_pages = int(result.get("pages") or 0)
        expected_pages = max(reported_pages, (total + self.page_size - 1) // self.page_size)
        if total <= 0 or expected_pages <= 0:
            raise RuntimeError(f"Eastmoney returned no valuation result for {trade_date}")
        payloads = [first]
        raw_pages = [first_raw]
        for page in range(2, expected_pages + 1):
            payload, raw = self._page(trade_date, page)
            page_result = payload.get("result") or {}
            if not page_result.get("data"):
                raise RuntimeError(f"Eastmoney returned empty page {page} of {expected_pages} for {trade_date}")
            payloads.append(payload)
            raw_pages.append(raw)
        raw_rows = [row for payload in payloads for row in ((payload.get("result") or {}).get("data") or [])]
        if len(raw_rows) != total:
            raise RuntimeError(f"Eastmoney pagination incomplete for {trade_date}: expected {total}, got {len(raw_rows)}")
        symbols = [str(row.get("SECUCODE") or "") for row in raw_rows]
        if len(set(symbols)) != len(symbols):
            raise RuntimeError(f"Eastmoney returned duplicate symbols for {trade_date}")
        raw_bytes = b"\n".join(raw_pages)
        raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        fetched_at = _fetched_at()
        return FetchedRows(
            dataset="valuation_daily", raw_bytes=raw_bytes,
            rows=normalize_eastmoney_valuation_rows(raw_rows, raw_sha256=raw_sha256, fetched_at=fetched_at, adapter_version=EASTMONEY_ADAPTER_VERSION),
            source=self.source, fetched_at=fetched_at,
        )


def sh_sz_a_lifecycle_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Retain A-share equity rows only; excludes indices, funds, bonds and Beijing."""
    allowed: list[dict[str, Any]] = []
    for row in rows:
        code = str(row.get("code") or "").lower()
        if str(row.get("type")) != "1":
            continue
        if (code.startswith("sh.") and code[3:5] in {"60", "68", "90"}) or (
            code.startswith("sz.") and code[3:5] in {"00", "30", "20"}
        ):
            allowed.append(row)
    return allowed


def _baostock_code(symbol: str) -> str:
    raw = str(symbol).upper()
    if raw.endswith(".SH") and raw[:6].isdigit() and raw[:2] in {"60", "68", "90"}:
        return f"sh.{raw[:6]}"
    if raw.endswith(".SZ") and raw[:6].isdigit() and raw[:2] in {"00", "30", "20"}:
        return f"sz.{raw[:6]}"
    raise ValueError(f"DataHub V1 supports Shanghai/Shenzhen A shares only: {symbol!r}")


class BaostockAdapter:
    source = "baostock"

    def __init__(self, *, host: str | None = None) -> None:
        self.host = host

    @staticmethod
    def _module():
        try:
            import baostock as bs
        except ImportError as exc:  # pragma: no cover - environment provisioning
            raise RuntimeError("baostock is required for DataHub V1; install the datahub dependency set") from exc
        return bs

    @contextmanager
    def _session(self):
        bs = self._module()
        constants = None
        original_host = None
        if self.host:
            import baostock.common.contants as constants
            original_host = constants.BAOSTOCK_SERVER_IP
            constants.BAOSTOCK_SERVER_IP = self.host
        import baostock.common.context as context
        import baostock.util.socketutil as socketutil

        old_timeout = socket.getdefaulttimeout()
        original_connect = socketutil.SocketUtil.connect

        def bounded_connect(instance):
            original_connect(instance)
            if hasattr(context, "default_socket"):
                context.default_socket = _EofFailingSocket(context.default_socket)

        socket.setdefaulttimeout(_BAOSTOCK_SESSION_SECONDS)
        socketutil.SocketUtil.connect = bounded_connect
        try:
            login = bs.login()
            if login.error_code != "0":
                raise RuntimeError(f"baostock login failed: {login.error_code} {login.error_msg}")
            yield bs
        finally:
            try:
                bs.logout()
            finally:
                socketutil.SocketUtil.connect = original_connect
                socket.setdefaulttimeout(old_timeout)
                if constants is not None:
                    constants.BAOSTOCK_SERVER_IP = original_host

    @staticmethod
    def _rows(result: Any, *, max_rows: int = _BAOSTOCK_MAX_ROWS) -> list[dict[str, Any]]:
        if result.error_code != "0":
            raise RuntimeError(f"baostock query failed: {result.error_code} {result.error_msg}")
        rows: list[dict[str, Any]] = []
        while result.next():
            rows.append(dict(zip(result.fields, result.get_row_data())))
            if len(rows) > max_rows:
                raise RuntimeError(f"baostock result exceeded row limit {max_rows}")
        return rows

    def valuation(self, symbol: str, start_date: str, end_date: str) -> FetchedRows:
        return next(rows for _, rows in self.valuations([symbol], start_date, end_date))

    def valuations(self, symbols: Iterable[str], start_date: str, end_date: str):
        """Fetch a bounded batch under one authenticated BaoStock session."""
        fields = "date,code,close,peTTM,pbMRQ,psTTM,pcfNcfTTM,turn,tradestatus,isST"
        with self._session() as bs:
            for symbol in symbols:
                code = _baostock_code(symbol)
                raw_rows = self._rows(
                    bs.query_history_k_data_plus(code, fields, start_date=start_date, end_date=end_date, frequency="d", adjustflag="3")
                )
                raw_bytes = pd.DataFrame(raw_rows).to_csv(index=False).encode("utf-8")
                import hashlib

                fetched_at = _fetched_at()
                yield symbol, FetchedRows(
                    dataset="valuation_daily",
                    raw_bytes=raw_bytes,
                    rows=normalize_valuation_rows(raw_rows, source=self.source, raw_sha256=hashlib.sha256(raw_bytes).hexdigest(), fetched_at=fetched_at, adapter_version=ADAPTER_VERSION),
                    source=self.source,
                    fetched_at=fetched_at,
                )

    def daily_bundles(self, symbols: Iterable[str], start_date: str, end_date: str):
        """Fetch one raw daily response per security and emit status candidates only."""
        fields = "date,code,open,high,low,close,volume,amount,turn,tradestatus,isST"
        with self._session() as bs:
            for symbol in symbols:
                raw_rows = self._rows(
                    bs.query_history_k_data_plus(
                        _baostock_code(symbol), fields, start_date=start_date,
                        end_date=end_date, frequency="d", adjustflag="3",
                    )
                )
                raw_bytes = pd.DataFrame(raw_rows).to_csv(index=False).encode("utf-8")
                raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
                fetched_at = _fetched_at()
                bundle = normalize_baostock_daily_bundle(
                    raw_rows, raw_sha256=raw_sha256, fetched_at=fetched_at,
                    adapter_version=ADAPTER_VERSION,
                )
                yield symbol, FetchedRows(
                    dataset="trade_status_daily", raw_bytes=raw_bytes,
                    rows=bundle["trade_status"], source=self.source,
                    fetched_at=fetched_at,
                )

    def lifecycle(self) -> FetchedRows:
        with self._session() as bs:
            raw_rows = sh_sz_a_lifecycle_rows(self._rows(bs.query_stock_basic()))
        raw_bytes = pd.DataFrame(raw_rows).to_csv(index=False).encode("utf-8")
        import hashlib

        fetched_at = _fetched_at()
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()
        return FetchedRows(
            dataset="security_lifecycle",
            raw_bytes=raw_bytes,
            rows=[normalize_lifecycle_row(row, raw_sha256=raw_hash, fetched_at=fetched_at, adapter_version=ADAPTER_VERSION) for row in raw_rows],
            source=self.source,
            fetched_at=fetched_at,
        )


class SwIndustryAdapter:
    source = "swsresearch"

    def __init__(self, *, ca_bundle: str | None = None) -> None:
        self.ca_bundle = ca_bundle

    def history(self) -> FetchedRows:
        response = requests.get(SW_URL, headers={"User-Agent": "QuantRadar DataHub/1"}, timeout=60, verify=self.ca_bundle or True)
        response.raise_for_status()
        raw_bytes = response.content
        raw = pd.read_excel(BytesIO(raw_bytes))
        renamed = raw.rename(columns={"股票代码": "code", "计入日期": "start_date", "行业代码": "industry_code", "更新日期": "update_date"})
        required = {"code", "start_date", "industry_code"}
        missing = required - set(renamed.columns)
        if missing:
            raise RuntimeError(f"SW industry schema changed; missing {sorted(missing)}")
        rows = renamed.to_dict("records")
        import hashlib

        fetched_at = _fetched_at()
        return FetchedRows(
            dataset="sw_industry_history",
            raw_bytes=raw_bytes,
            rows=build_sw_level_one_intervals(rows, raw_sha256=hashlib.sha256(raw_bytes).hexdigest(), fetched_at=fetched_at, adapter_version=ADAPTER_VERSION),
            source=self.source,
            fetched_at=fetched_at,
        )
