"""FactorLab batch jobs: fixed inputs, disk artifacts, and PostgreSQL task index."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .cache import cache_key, operator_bundle_hash
from .evaluation import EVALUATION_VERSION, evaluate, forward_open_label, split_dates, dates_within_label_window

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="factorlab")


def _hash_members(members: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(members)).encode()).hexdigest()


def _research_input_version() -> str:
    root = Path(__file__).resolve().parents[1]
    source = root / "datahub" / "research_inputs.py"
    return hashlib.sha256(source.read_bytes()).hexdigest()


def create_batch(config: dict[str, Any]) -> dict[str, Any]:
    release_id, members = str(config.get("release_id") or ""), sorted(set(config.get("members") or []))
    if not release_id or len(members) < 20:
        raise ValueError("release_id and at least 20 explicit pool members are required")
    try:
        ids = [int(x) for x in config.get("alpha_ids") or []]
        horizons = [int(x) for x in config.get("horizons", [1, 5, 20])]
    except (TypeError, ValueError) as exc:
        raise ValueError("alpha_ids and horizons must be integers") from exc
    if not horizons or any(x not in (1, 5, 20) for x in horizons):
        raise ValueError("horizons must be a non-empty subset of 1, 5, 20")
    from quantradar.datahub.alpha101.catalog import dependency_matrix
    catalog = {r["alpha_id"]: r for r in dependency_matrix()}
    if not ids or any(i not in catalog for i in ids):
        raise ValueError("alpha_ids must contain implemented Alpha101 catalog entries")
    max_lookback = max(catalog[i]["lookback_days"] for i in ids)
    start = str(config.get("start_date") or "")
    calculation_start = (pd.Timestamp(start) - pd.Timedelta(days=max_lookback * 2 + 20)).date().isoformat() if start else ""
    from quantradar.config import load_datahub_config
    from quantradar.datahub.reader import ReleaseReader
    scope = ReleaseReader(load_datahub_config()).resolve(release_id)
    ratios = tuple(float(x) for x in config.get("split_ratios", [.6, .2, .2]))
    # Validate at submission time, before a task has been persisted or queued.
    split_dates(pd.date_range("2000-01-01", periods=10), ratios)
    frozen = {"release_id": scope.release_id, "base_commit": scope.manifest["base_commit"], "supplemental_commit": scope.manifest["supplemental_commit"], "members": members, "members_hash": _hash_members(members),
              "pool_type": config.get("pool_type", "CUSTOM_STATIC_POOL"), "snapshot_date": config.get("snapshot_date"),
              "start_date": start, "calculation_start": calculation_start, "end_date": str(config.get("end_date") or ""),
              "alpha_ids": ids, "horizons": horizons, "split_ratios": list(ratios), "price_mode": "RAW",
              "adv_basis": "amount", "min_cross_section": int(config.get("min_cross_section", 20)),
              "unit_contract": "base-hands-thousand-yuan", "research_input_version": _research_input_version(),
              "operator_bundle_hash": operator_bundle_hash(), "status": "PENDING", "items": []}
    if not frozen["start_date"] or not frozen["end_date"] or frozen["start_date"] > frozen["end_date"]:
        raise ValueError("valid start_date/end_date are required")
    from quantradar.storage import init_db, save_experiment
    init_db()
    batch = save_experiment("FactorLab 批次", "factor", frozen, "", {}, None, source_refs={"release_id": release_id})
    _EXECUTOR.submit(_run, batch.experiment_id, frozen)
    return batch.to_dict()


def _panel(config: dict[str, Any]) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    from quantradar.config import load_datahub_config
    from quantradar.datahub.reader import ReleaseReader
    from quantradar.datahub.research_inputs import standard_panel
    scope = ReleaseReader(load_datahub_config()).resolve(config["release_id"])
    reader = ReleaseReader(load_datahub_config())
    # A-share OHLCV is a reusable fact in the immutable base Dolt.  The
    # supplement is not a replacement warehouse for it.
    conn = reader.base_connection(scope)
    base_rows = {}
    for symbol in config["members"]:
        code, exchange = symbol.split(".")
        internal = exchange + code
        values = conn.query("SELECT tradedate, open, high, low, close, volume, amount "
                            "FROM final_a_stock_eod_price WHERE symbol=%s AND tradedate >= %s AND tradedate <= %s ORDER BY tradedate",
                            (internal, config.get("calculation_start", config["start_date"]), config["end_date"]))
        base_rows[symbol] = [dict(row, trade_date=row.pop("tradedate"), unit_contract_version="base-hands-thousand-yuan") for row in values]
    rows = base_rows
    all_rows = []
    for symbol, values in rows.items():
        if not values: continue
        raw = pd.DataFrame(values)
        contract = str(raw.unit_contract_version.dropna().iloc[0]) if "unit_contract_version" in raw and raw.unit_contract_version.notna().any() else "joinquant-shares-yuan-v2"
        normalized = standard_panel(raw, unit_contract=contract, adjustment="raw")
        normalized["trade_date"] = pd.to_datetime(raw.trade_date).values; normalized["symbol"] = symbol
        all_rows.append(normalized)
    if not all_rows: raise ValueError("no published A-share raw prices for selected pool")
    frame = pd.concat(all_rows, ignore_index=True)
    fields = {name: frame.pivot(index="trade_date", columns="symbol", values=name).sort_index() for name in ("open", "high", "low", "close", "volume_shares", "amount_cny", "vwap", "returns")}
    fields["volume"] = fields.pop("volume_shares"); fields["amount"] = fields.pop("amount_cny")
    # Membership is explicit and intentionally independent of per-day price
    # availability: missing facts must remain visible to qualification.
    fields["universe"] = pd.DataFrame(True, index=fields["close"].index, columns=fields["close"].columns)
    return fields, fields["open"]


def _run(batch_id: str, config: dict[str, Any]) -> None:
    from quantradar.datahub.alpha101.catalog import compute, dependency_matrix
    from quantradar.storage import update_experiment
    config["status"] = "RUNNING"; update_experiment(batch_id, config=config)
    root = Path.cwd() / "runs" / "factorlab" / batch_id; root.mkdir(parents=True, exist_ok=True)
    try:
        panel, opens = _panel(config)
        requested_dates = opens.loc[config["start_date"]:config["end_date"]].index
        splits = split_dates(requested_dates, tuple(config["split_ratios"]))
        config["split_dates"] = {name: [str(pd.Timestamp(x).date()) for x in dates] for name, dates in splits.items()}
        catalog = {r["alpha_id"]: r for r in dependency_matrix()}
        from .qualification import batch_status, preflight
        for alpha_id in config["alpha_ids"]:
            row = catalog[alpha_id]
            qualification = preflight(set(panel), set(row["fields"]))
            if qualification["status"] != "READY":
                config["items"].append({"alpha_id": alpha_id, **qualification})
                update_experiment(batch_id, config=config)
                continue
            calc_identity = {k: config[k] for k in ("release_id", "base_commit", "supplemental_commit", "members_hash", "pool_type", "snapshot_date", "calculation_start", "start_date", "end_date", "price_mode", "unit_contract", "adv_basis", "operator_bundle_hash", "research_input_version")}
            calc_identity.update({"alpha_id": alpha_id, "formula_hash": row["formula_hash"], "semantics_version": row["semantics_version"]})
            key = cache_key(calc_identity); value_path = root / "factor_values" / f"alpha{alpha_id:03}_{key}.parquet"; value_path.parent.mkdir(exist_ok=True)
            calc_cache = Path.cwd() / "runs" / "factorlab" / "cache" / "calculation" / f"{key}.parquet"; calc_cache.parent.mkdir(parents=True, exist_ok=True)
            if calc_cache.exists(): factor = pd.read_parquet(calc_cache); factor.index = pd.to_datetime(factor.index); calc_status = "CACHE_HIT"
            else:
                factor = compute(alpha_id, panel, adv_basis="amount", price_mode="RAW")
                factor.to_parquet(calc_cache); calc_status = "COMPUTED"
            factor.to_parquet(value_path)
            evaluations = {}
            for horizon in config["horizons"]:
                eligible = {scope: dates_within_label_window(dates, requested_dates, horizon) for scope, dates in splits.items()}
                ekey = cache_key({"calculation_key": key, "label": "open(t+h+1)/open(t+1)-1", "horizon": horizon, "splits": config["split_dates"], "min_cross_section": config["min_cross_section"], "quantiles": "average_rank_5", "ic_method": "qlib_calc_ic", "direction_policy": "no_flip", "evaluation": EVALUATION_VERSION})
                epath = root / "evaluation" / f"alpha{alpha_id:03}_h{horizon}_{ekey}.json"; epath.parent.mkdir(exist_ok=True)
                eval_cache = Path.cwd() / "runs" / "factorlab" / "cache" / "evaluation" / f"{ekey}.json"; eval_cache.parent.mkdir(parents=True, exist_ok=True)
                if eval_cache.exists(): result = json.loads(eval_cache.read_text()); status = "CACHE_HIT"
                else:
                    label = forward_open_label(opens, horizon)
                    # Holdout remains uncomputed until an explicit, immutable user selection.
                    result = {scope: evaluate(factor.loc[dates], label.loc[dates], min_cross_section=config["min_cross_section"])
                              for scope, dates in eligible.items() if scope != "holdout"}
                    eval_cache.write_text(json.dumps(result)); status = "EVALUATED"
                epath.write_text(json.dumps(result))
                validation = result.get("validation", {})
                evaluations[str(horizon)] = {"status": status, "artifact": str(epath), "summary": {k: validation.get(k) for k in ("valid_dates", "ic_mean", "rank_ic_mean", "rank_ic_std", "rank_ic_positive_ratio", "rank_ic_positive_month_ratio", "mean_cross_section", "top_quantile_turnover")}, "scopes": result}
            item_status = "FORMULA_EMPTY_VALID" if factor.notna().sum().sum() == 0 else "COMPUTED"
            config["items"].append({"alpha_id": alpha_id, "status": item_status, "calculation": calc_status, "value_artifact": str(value_path), "evaluations": evaluations})
            update_experiment(batch_id, config=config)
        config["status"] = batch_status([str(item["status"]) for item in config["items"]])
        fingerprint = cache_key({
            "release_id": config["release_id"], "base_commit": config["base_commit"],
            "supplemental_commit": config["supplemental_commit"], "members_hash": config["members_hash"],
            "split_dates": config["split_dates"], "alpha_ids": config["alpha_ids"], "horizons": config["horizons"],
            "results": [{"alpha_id": item["alpha_id"], "evaluations": {h: v["summary"] for h, v in item["evaluations"].items()}}
                        for item in config["items"]],
        })
    except Exception as exc:
        config["status"] = "FAILED"; config["error"] = str(exc)
    update_experiment(batch_id, config=config,
                      result_fingerprint=fingerprint if config["status"] in {"SUCCESS", "PARTIAL_SUCCESS", "BLOCKED"} else None)


def evaluate_holdout(batch_id: str) -> dict[str, Any]:
    """Evaluate only frozen representatives on the previously unseen holdout split."""
    from quantradar.storage import get_experiment, update_experiment
    row = get_experiment(batch_id)
    if not row or row.get("kind") != "factor":
        raise ValueError("FactorLab batch does not exist")
    config = row.get("config") or {}
    selection = config.get("representative_selection")
    if not selection:
        raise ValueError("freeze representative factors before accessing holdout")
    if config.get("holdout_access"):
        return config["holdout_access"]
    panel, opens = _panel(config)
    requested_dates = opens.loc[config["start_date"]:config["end_date"]].index
    split = split_dates(requested_dates, tuple(config["split_ratios"]))["holdout"]
    output: dict[str, Any] = {"accessed_at": pd.Timestamp.now(tz="UTC").isoformat(), "alpha_ids": selection["alpha_ids"], "evaluations": {}}
    root = (Path.cwd() / "runs" / "factorlab" / batch_id).resolve()
    by_id = {int(x["alpha_id"]): x for x in config.get("items", [])}
    for alpha_id in selection["alpha_ids"]:
        item = by_id[int(alpha_id)]
        value_path = Path(item["value_artifact"]).resolve()
        if not value_path.is_file() or root not in value_path.parents:
            raise ValueError("registered factor artifact is unavailable")
        factor = pd.read_parquet(value_path); factor.index = pd.to_datetime(factor.index)
        for horizon in config["horizons"]:
            dates = dates_within_label_window(split, requested_dates, int(horizon))
            label = forward_open_label(opens, int(horizon))
            result = evaluate(factor.loc[dates], label.loc[dates], min_cross_section=config["min_cross_section"])
            output["evaluations"].setdefault(str(alpha_id), {})[str(horizon)] = result
    path = root / "evaluation" / "holdout_representatives.json"; path.write_text(json.dumps(output))
    output["artifact"] = str(path)
    config["holdout_access"] = output
    update_experiment(batch_id, config=config)
    return output
