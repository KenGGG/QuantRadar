#!/usr/bin/env python3
"""Inspect QuantRadar candidate SDK contracts without fetching market data.

Usage:
    python quantradar_data_interfaces_check.py --output /tmp/interface_contract_report.json
    python quantradar_data_interfaces_check.py --only baostock

Each SDK is imported in an isolated subprocess with outgoing sockets disabled.
No login/data function is called, no package is installed/upgraded, and no
QuantRadar database or release is modified. Successful inspection is NOT a
network-health, unit-semantics, historical-coverage or PIT qualification.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib
import importlib.metadata
import inspect
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Callable

sys.dont_write_bytecode = True

# These are example invocation contracts, not data calls or completeness claims.
CONTRACTS: dict[str, dict[str, dict[str, Any]]] = {
    "baostock": {
        "query_history_k_data_plus": {
            "code": "sh.600519", "fields": "date,code,open,high,low,close,volume,amount,tradestatus,isST",
            "start_date": "2020-01-01", "end_date": "2026-08-31", "frequency": "d", "adjustflag": "3",
        },
        "query_stock_basic": {"code": "sh.600519"},
        "query_all_stock": {"day": "2020-01-02"},
        "query_trade_dates": {"start_date": "2020-01-01", "end_date": "2026-08-31"},
        "query_adjust_factor": {"code": "sh.600519", "start_date": "2020-01-01", "end_date": "2026-08-31"},
        "query_dividend_data": {"code": "sh.600519", "year": "2020", "yearType": "operate"},
        "query_hs300_stocks": {"date": "2020-01-02"},
        "query_zz500_stocks": {"date": "2020-01-02"},
    },
    "akshare": {
        "stock_zh_a_hist_tx": {
            "symbol": "sz000001", "start_date": "20200101", "end_date": "20260831", "adjust": "", "timeout": 30,
        },
        "stock_value_em": {"symbol": "600519"},
        "stock_zh_valuation_baidu": {"symbol": "600519", "indicator": "总市值", "period": "全部"},
        "stock_dividend_cninfo": {"symbol": "600519"},
        "stock_industry_clf_hist_sw": {},
        "sw_index_first_info": {},
        "sw_index_second_info": {},
        "sw_index_third_info": {},
        "index_stock_cons_csindex": {"symbol": "000300"},
        "index_stock_cons_weight_csindex": {"symbol": "000300"},
        "fund_etf_category_sina": {"symbol": "ETF基金"},
        "fund_etf_spot_em": {},
        "fund_etf_hist_em": {
            "symbol": "510300", "period": "daily", "start_date": "20200101", "end_date": "20260831", "adjust": "",
        },
        "fund_etf_hist_sina": {"symbol": "sh510300"},
        "fund_fh_em": {"year": "2020", "typ": "", "rank": "BZDM", "sort": "asc", "page": 1},
        "fund_cf_em": {"year": "2020", "typ": "", "rank": "FSRQ", "sort": "desc", "page": 1},
        "fund_announcement_dividend_em": {"symbol": "510300"},
        "fund_etf_dividend_sina": {"symbol": "sh510050"},
        "fund_etf_fund_info_em": {"fund": "510300", "start_date": "20200101", "end_date": "20260831"},
        "stock_info_sz_delist": {"symbol": "终止上市公司"},
        "stock_info_sh_delist": {"symbol": "全部"},
        "stock_zh_a_st_em": {},
    },
}


def inspect_callable(fn: Callable[..., Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Inspect a callable; never invoke it."""
    result: dict[str, Any] = {"network_test": "NOT_NETWORK_TESTED", "example_kwargs": kwargs}
    try:
        sig = inspect.signature(fn)
        result["signature"] = str(sig)
        sig.bind(**kwargs)
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            result["status"] = "WRAPPER_SIGNATURE_UNVERIFIED"
        else:
            result["status"] = "SIGNATURE_COMPATIBLE_NOT_NETWORK_TESTED"
    except (TypeError, ValueError) as exc:
        result.update(status="SIGNATURE_MISMATCH_OR_UNAVAILABLE", error=str(exc))
    try:
        source_file = inspect.getsourcefile(fn)
        result["source_file"] = source_file
        if source_file and Path(source_file).is_file():
            result["source_file_sha256"] = hashlib.sha256(Path(source_file).read_bytes()).hexdigest()
    except (OSError, TypeError) as exc:
        result["source_inspection_error"] = str(exc)
    return result


def worker(module_name: str) -> dict[str, Any]:
    # This process is dedicated to inspection; patches cannot affect the user's
    # running application. No market API/login callable below is invoked.
    import socket

    def deny_network(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Network access is disabled during offline SDK inspection")

    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    out: dict[str, Any] = {"module": module_name, "network_test": "NOT_NETWORK_TESTED", "functions": {}}
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            module = importlib.import_module(module_name)
        try:
            out["installed_version"] = importlib.metadata.version(module_name)
        except importlib.metadata.PackageNotFoundError:
            out["installed_version"] = getattr(module, "__version__", None)
        for name, kwargs in CONTRACTS[module_name].items():
            fn = getattr(module, name, None)
            out["functions"][name] = (
                inspect_callable(fn, kwargs) if callable(fn)
                else {"status": "FUNCTION_MISSING", "network_test": "NOT_NETWORK_TESTED", "example_kwargs": kwargs}
            )
        out["status"] = "INSPECTED_NOT_NETWORK_TESTED"
    except Exception as exc:
        out.update(status="MODULE_IMPORT_FAILED", error=f"{type(exc).__name__}: {exc}")
    # Imported-library output is intentionally not copied into the report; it
    # may include unrelated environment details. Count it for transparency.
    out["suppressed_import_log_chars"] = len(captured.getvalue())
    return out


def run_worker(module_name: str, timeout: float) -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--_module", module_name],
            capture_output=True, text=True, timeout=timeout, check=False, env=env,
        )
        if completed.returncode != 0:
            return {"module": module_name, "status": "INSPECTION_PROCESS_FAILED", "returncode": completed.returncode}
        return json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        return {"module": module_name, "status": "INSPECTION_TIMEOUT", "timeout_seconds": timeout}
    except (OSError, json.JSONDecodeError) as exc:
        return {"module": module_name, "status": "INSPECTION_FAILED", "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Optional JSON report path; default prints JSON only")
    parser.add_argument("--only", choices=list(CONTRACTS), help="Inspect just one SDK")
    parser.add_argument("--timeout", type=float, default=30.0, help="Maximum import/inspection seconds per SDK")
    parser.add_argument("--_module", choices=list(CONTRACTS), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args._module:
        print(json.dumps(worker(args._module), ensure_ascii=False))
        return 0
    modules = [args.only] if args.only else list(CONTRACTS)
    results = [run_worker(name, args.timeout) for name in modules]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0],
        "status": "OFFLINE_INSPECTION_ONLY",
        "network_test": "NOT_NETWORK_TESTED",
        "coverage_test": "NOT_TESTED",
        "pit_test": "NOT_TESTED",
        "database_changes": False,
        "modules": results,
    }
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            # Refuse to overwrite an existing report or other user file.
            with args.output.open("x", encoding="utf-8") as f:
                f.write(payload + "\n")
        except OSError as exc:
            print(f"Could not create report: {exc}", file=sys.stderr)
            return 1
        print(f"Created offline report: {args.output}")
    else:
        print(payload)
    compatible = all(
        m.get("status") == "INSPECTED_NOT_NETWORK_TESTED"
        and all(row.get("status") == "SIGNATURE_COMPATIBLE_NOT_NETWORK_TESTED" for row in m["functions"].values())
        for m in results
    )
    # 2 means something requires local review, not that data APIs are down.
    return 0 if compatible else 2


if __name__ == "__main__":
    raise SystemExit(main())
