"""Release-pinned ETF_RAW research templates and dependency-aware preflight."""
from __future__ import annotations

from dataclasses import dataclass
import concurrent.futures
import json
from pathlib import Path
import threading
import uuid
from typing import Any

import numpy as np
import pandas as pd

ETF_POOL = ("510050.SH", "510180.SH", "510300.SH", "510500.SH", "510880.SH", "159901.SZ", "159902.SZ", "159903.SZ", "159915.SZ", "159919.SZ")
TEMPLATES = {
    "equal_weight": {"label": "定期等权", "lookback": 0},
    "momentum": {"label": "动量 Top-K", "lookback": 60},
    "trend": {"label": "趋势过滤", "lookback": 120},
    "inverse_vol": {"label": "逆波动率", "lookback": 61},
    "erc": {"label": "ERC 风险平价", "lookback": 61},
}
_GROUP_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="etf-group")
_GROUP_LOCK = threading.Lock()


def template_catalog() -> list[dict[str, Any]]:
    return [{"id": key, **value} for key, value in TEMPLATES.items()]


def load_close_panel(release_id: str, symbols: list[str], start: str, end: str) -> pd.DataFrame:
    from quantradar.config import load_datahub_config
    from quantradar.datahub.reader import ReleaseReader
    scope = ReleaseReader(load_datahub_config()).resolve(release_id)
    reader = ReleaseReader(load_datahub_config()).supplemental_reader(scope)
    # The displayed/evaluated interval starts at ``start``; signals may require
    # up to 120 prior trading observations.  Fetch a conservative calendar
    # warmup here rather than silently treating a valid historical window as a
    # data gap.
    read_start = (pd.Timestamp(start) - pd.Timedelta(days=220)).date().isoformat()
    rows = reader.etf_prices(symbols, read_start, end)
    records = [dict(item, symbol=symbol) for symbol, values in rows.items() for item in values]
    if not records:
        raise ValueError("所选 release 没有 ETF_RAW 日线")
    frame = pd.DataFrame(records)
    closes = frame.pivot(index="trade_date", columns="symbol", values="close").sort_index().astype(float)
    # The signal is t close and the order is submitted at t+1 open.  Preserve
    # the execution field alongside the close panel without changing the
    # public close-panel contract used by existing callers.
    closes.attrs["open"] = frame.pivot(index="trade_date", columns="symbol", values="open").sort_index().astype(float)
    return closes


def rebalance_dates(panel: pd.DataFrame, start: str, end: str) -> list[pd.Timestamp]:
    dates = pd.DatetimeIndex(pd.to_datetime(panel.index)).sort_values()
    dates = dates[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))]
    return [group.iloc[0] for _, group in pd.Series(dates, index=dates).groupby(dates.to_period("M")) if len(group)]


def preflight(panel: pd.DataFrame, template: str, start: str, end: str) -> dict[str, Any]:
    if template not in TEMPLATES:
        raise ValueError(f"unknown ETF template: {template}")
    lookback = TEMPLATES[template]["lookback"]
    opens = panel.attrs.get("open")
    dates = rebalance_dates(panel, start, end)
    missing: list[dict[str, Any]] = []
    for effective in dates:
        loc = panel.index.get_indexer([effective])[0]
        # ``effective`` is t+1.  All research inputs end at the prior close.
        if lookback and loc < lookback + 1:
            missing.append({"template": template, "effective_date": str(pd.Timestamp(effective).date()),
                            "date": None, "security": "*", "field": f"{lookback}_day_warmup"})
            continue
        needed = panel.iloc[loc - lookback : loc] if lookback else panel.iloc[0:0]
        for day, row in needed.iterrows():
            for symbol in row.index[row.isna()]:
                missing.append({"template": template, "effective_date": str(pd.Timestamp(effective).date()),
                                "date": str(pd.Timestamp(day).date()), "security": symbol, "field": "close"})
        if opens is not None:
            signal = panel.iloc[loc - 1]
            if template == "equal_weight": targets = list(panel.columns)
            elif template == "momentum": targets = sorted((signal / panel.iloc[loc - 1 - 60] - 1).nlargest(3).index)
            elif template == "trend": targets = list(signal[signal > panel.iloc[loc - 120 : loc].mean()].index)
            else: targets = list(panel.columns)
            for symbol in targets:
                if pd.isna(opens.loc[effective, symbol]):
                    missing.append({"template": template, "effective_date": str(pd.Timestamp(effective).date()),
                                    "date": str(pd.Timestamp(effective).date()), "security": symbol, "field": "open"})
    return {"template": template, "lookback": lookback, "rebalance_dates": [str(d.date()) for d in dates],
            "blocked": bool(missing), "missing": missing}


def _erc(cov: pd.DataFrame) -> pd.Series:
    n = len(cov)
    if n == 0 or not np.isfinite(cov.to_numpy()).all():
        raise ValueError("ERC covariance is invalid")
    w = np.repeat(1 / n, n)
    matrix = cov.to_numpy()
    for _ in range(1000):
        marginal = matrix @ w
        rc = w * marginal
        if np.any(rc <= 0) or not np.isfinite(rc).all():
            raise ValueError("ERC risk contribution is invalid")
        target = rc.mean()
        next_w = w * target / rc
        next_w /= next_w.sum()
        if np.max(np.abs(next_w * (matrix @ next_w) / (next_w @ matrix @ next_w) - 1 / n)) <= 0.01:
            return pd.Series(next_w, index=cov.index)
        w = next_w
    raise ValueError("ERC did not converge to the configured risk budget")


def build_weights(panel: pd.DataFrame, template: str, start: str, end: str, *, momentum_days: int = 60,
                  top_k: int = 3, trend_days: int = 120, volatility_days: int = 60) -> pd.DataFrame:
    check = preflight(panel, template, start, end)
    if check["blocked"]:
        raise ValueError(f"ETF preflight blocked: {len(check['missing'])} required observations missing")
    rows: list[dict[str, Any]] = []
    for effective in pd.to_datetime(check["rebalance_dates"]):
        loc = panel.index.get_indexer([effective])[0]
        # Signal t close, execute at the following trading day's open.
        signal_loc = loc - 1
        close = panel.iloc[signal_loc]
        reason = template
        if template == "equal_weight":
            weights = pd.Series(1 / len(close), index=close.index)
        elif template == "momentum":
            score = close / panel.iloc[signal_loc - momentum_days] - 1
            winners = sorted(score.nlargest(top_k).index)
            weights = pd.Series(1 / len(winners), index=winners)
        elif template == "trend":
            eligible = close[close > panel.iloc[loc - trend_days : loc].mean()]
            weights = pd.Series(1 / len(eligible), index=eligible.index) if len(eligible) else pd.Series(dtype=float)
        else:
            returns = panel.iloc[signal_loc - volatility_days : signal_loc + 1].pct_change().iloc[1:]
            if template == "inverse_vol":
                inverse = 1 / returns.std(ddof=1)
                weights = inverse / inverse.sum()
            else:
                weights = _erc(returns.cov())
        signal_date = panel.index[signal_loc]
        for security, weight in weights.items():
            rows.append({"signal_date": str(pd.Timestamp(signal_date).date()), "effective_date": str(pd.Timestamp(effective).date()),
                         "security": security, "target_weight": float(weight), "signal_value": reason, "reason": reason})
    return pd.DataFrame(rows)


def create_experiment_group(*, release_id: str, start: str, end: str, templates: list[str],
                            initial_cash: float = 500000, slippage_bps: float = 0) -> dict[str, Any]:
    """Persist a group and serially enqueue real Worker runs.

    The group executor has one worker intentionally: BulletTrade's provider/FQ
    state is process-global, so exposing Worker pool slots as parallel ETF runs
    would be misleading.
    """
    if slippage_bps < 0 or not np.isfinite(slippage_bps):
        raise ValueError("slippage_bps must be a finite non-negative number")
    panel = load_close_panel(release_id, list(ETF_POOL), start, end)
    checks = {template: preflight(panel, template, start, end) for template in templates}
    from quantradar.config import load_datahub_config
    from quantradar.datahub.reader import ReleaseReader
    scope = ReleaseReader(load_datahub_config()).resolve(release_id)
    from quantradar.storage import init_db, save_experiment
    init_db()
    config = {"release_id": scope.release_id, "base_commit": scope.manifest["base_commit"],
              "supplemental_commit": scope.manifest["supplemental_commit"], "start_date": start, "end_date": end,
              "templates": templates, "initial_cash": initial_cash, "slippage_bps": slippage_bps,
              "engine_slippage_ratio": 2 * slippage_bps / 10000,
              "items": [{"template": t, "status": "PRECHECK_BLOCKED" if checks[t]["blocked"] else "WAITING", "preflight": checks[t]} for t in templates]}
    group = save_experiment("ETF 研究组", "etf_group", config, "", {}, None,
                            source_refs={"release": {k: config[k] for k in ("release_id", "base_commit", "supplemental_commit")}})
    _GROUP_EXECUTOR.submit(_run_group, group.experiment_id, panel, config)
    return group.to_dict()


def _run_group(experiment_id: str, panel: pd.DataFrame, config: dict[str, Any]) -> None:
    from quantradar.portfolio.target_weight_bridge import build_effective_weight_strategy
    from quantradar.storage import update_experiment
    from quantradar.worker import get_worker
    root = Path.cwd() / "runs" / "etf_groups" / experiment_id
    root.mkdir(parents=True, exist_ok=True)
    items = config["items"]
    for item in items:
        # Recovery is idempotent: a persisted child run is authoritative.  Do
        # not submit the same template again merely because the group process
        # was restarted while the Worker was already handling it.
        if item.get("run_id"):
            existing = get_worker().get_status(item["run_id"])
            if existing is not None:
                item["status"] = existing["status"]
                item["error"] = existing.get("error")
                update_experiment(experiment_id, config=config)
                continue
        if item["status"] != "WAITING":
            continue
        item["status"] = "SUBMITTED"; update_experiment(experiment_id, config=config)
        try:
            weights = build_weights(panel, item["template"], config["start_date"], config["end_date"])
            path = root / f"{item['template']}_weights.csv"; weights.to_csv(path, index=False)
            cost = {"open_tax": 0, "close_tax": 0, "open_commission": 0.0003, "close_commission": 0.0003,
                    "min_commission": 5, "slippage_ratio": config["engine_slippage_ratio"]}
            code = build_effective_weight_strategy(path, etf_raw=True, order_cost=cost,
                                                   slippage_ratio=config["engine_slippage_ratio"])
            result = get_worker().submit({"code": code, "start_date": config["start_date"], "end_date": config["end_date"],
                                          "initial_cash": config["initial_cash"], "frequency": "day", "benchmark": None,
                                          "fq": "none", "release_id": config["release_id"], "strategy_name": f"ETF {item['template']}",
                                          "extras": {"etf_research": {"template": item["template"], "weight_artifact": str(path), "cost": cost}}})
            item["run_id"] = result["run_id"]; item["status"] = "PENDING"; update_experiment(experiment_id, config=config)
            get_worker().wait(result["run_id"], timeout=None)
            status = get_worker().get_status(result["run_id"])
            item["status"] = status["status"]; item["error"] = status.get("error")
        except Exception as exc:
            item["status"] = "FAILED"; item["error"] = str(exc)
        update_experiment(experiment_id, config=config)
