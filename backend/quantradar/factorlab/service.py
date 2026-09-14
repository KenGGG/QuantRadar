"""FactorLab batch jobs: fixed inputs, disk artifacts, and PostgreSQL task index."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .cache import cache_key, operator_bundle_hash
from .evaluation import evaluate, forward_open_label

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="factorlab")


def _hash_members(members: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(members)).encode()).hexdigest()


def create_batch(config: dict[str, Any]) -> dict[str, Any]:
    release_id, members = str(config.get("release_id") or ""), sorted(set(config.get("members") or []))
    if not release_id or len(members) < 20:
        raise ValueError("release_id and at least 20 explicit pool members are required")
    ids = [int(x) for x in config.get("alpha_ids") or []]
    from quantradar.datahub.alpha101.catalog import dependency_matrix
    catalog = {r["alpha_id"]: r for r in dependency_matrix()}
    if not ids or any(i not in catalog or catalog[i]["group"] != "price_volume" for i in ids):
        raise ValueError("alpha_ids must contain only price_volume catalog entries")
    max_lookback = max(catalog[i]["lookback_days"] for i in ids)
    start = str(config.get("start_date") or "")
    calculation_start = (pd.Timestamp(start) - pd.Timedelta(days=max_lookback * 2 + 20)).date().isoformat() if start else ""
    frozen = {"release_id": release_id, "members": members, "members_hash": _hash_members(members),
              "pool_type": config.get("pool_type", "CUSTOM_STATIC_POOL"), "snapshot_date": config.get("snapshot_date"),
              "start_date": start, "calculation_start": calculation_start, "end_date": str(config.get("end_date") or ""),
              "alpha_ids": ids, "horizons": config.get("horizons", [1, 5, 20]), "price_mode": "RAW",
              "adv_basis": "amount", "min_cross_section": int(config.get("min_cross_section", 20)),
              "operator_bundle_hash": operator_bundle_hash(), "status": "PENDING", "items": []}
    if not frozen["start_date"] or not frozen["end_date"] or frozen["start_date"] > frozen["end_date"]:
        raise ValueError("valid start_date/end_date are required")
    from quantradar.storage import save_experiment
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
    fields["universe"] = fields["close"].notna()
    return fields, fields["open"]


def _run(batch_id: str, config: dict[str, Any]) -> None:
    from quantradar.datahub.alpha101.catalog import compute, dependency_matrix
    from quantradar.storage import update_experiment
    config["status"] = "RUNNING"; update_experiment(batch_id, config=config)
    root = Path.cwd() / "runs" / "factorlab" / batch_id; root.mkdir(parents=True, exist_ok=True)
    try:
        panel, opens = _panel(config)
        catalog = {r["alpha_id"]: r for r in dependency_matrix()}
        for alpha_id in config["alpha_ids"]:
            row = catalog[alpha_id]
            calc_identity = {k: config[k] for k in ("release_id", "members_hash", "start_date", "end_date", "price_mode", "adv_basis", "operator_bundle_hash")}
            calc_identity.update({"alpha_id": alpha_id, "formula_hash": row["formula_hash"], "semantics_version": row["semantics_version"]})
            key = cache_key(calc_identity); value_path = root / "factor_values" / f"alpha{alpha_id:03}_{key}.parquet"; value_path.parent.mkdir(exist_ok=True)
            if value_path.exists(): factor = pd.read_parquet(value_path); factor.index = pd.to_datetime(factor.index); calc_status = "CACHE_HIT"
            else: factor = compute(alpha_id, panel, adv_basis="amount", price_mode="RAW"); factor.to_parquet(value_path); calc_status = "COMPUTED"
            evaluations = {}
            for horizon in config["horizons"]:
                ekey = cache_key({"calculation_key": key, "horizon": horizon, "min_cross_section": config["min_cross_section"], "direction_policy": "no_flip", "evaluation": "factorlab-eval-v1"})
                epath = root / "evaluation" / f"alpha{alpha_id:03}_h{horizon}_{ekey}.json"; epath.parent.mkdir(exist_ok=True)
                if epath.exists(): result = json.loads(epath.read_text()); status = "CACHE_HIT"
                else:
                    label = forward_open_label(opens, horizon)
                    factor_eval = factor.loc[config["start_date"]:config["end_date"]]
                    result = evaluate(factor_eval, label.loc[factor_eval.index], min_cross_section=config["min_cross_section"])
                    epath.write_text(json.dumps(result)); status = "EVALUATED"
                evaluations[str(horizon)] = {"status": status, "artifact": str(epath), "summary": {k: result[k] for k in ("valid_dates", "ic_mean", "rank_ic_mean")}}
            config["items"].append({"alpha_id": alpha_id, "calculation": calc_status, "value_artifact": str(value_path), "evaluations": evaluations})
            update_experiment(batch_id, config=config)
        config["status"] = "SUCCESS"
    except Exception as exc:
        config["status"] = "FAILED"; config["error"] = str(exc)
    update_experiment(batch_id, config=config)
