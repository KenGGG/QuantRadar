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


def result_summary_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fingerprint completed and data-blocked items without inventing artifacts."""
    result = []
    for item in items:
        summary = {horizon: value.get("summary", {}) for horizon, value in item.get("evaluations", {}).items()}
        row = {"alpha_id": item["alpha_id"], "status": item["status"]}
        if summary:
            row["evaluations"] = summary
        if item.get("missing_fields"):
            row["missing_fields"] = item["missing_fields"]
        result.append(row)
    return result


def failed_engine_item(alpha_id: int, exc: Exception) -> dict[str, Any]:
    """Persist an isolated interpreter/evaluation failure without losing peers."""
    return {"alpha_id": alpha_id, "status": "FAILED_ENGINE",
            "error": f"{exc.__class__.__name__}: {exc}"}


def calculation_start_from_calendar(calendar: list[str], start_date: str, lookback_days: int) -> str:
    """Include the required warmup bars using immutable release sessions."""
    if not calendar:
        raise ValueError("fixed release has no trading calendar")
    position = pd.DatetimeIndex(pd.to_datetime(calendar)).searchsorted(pd.Timestamp(start_date), side="right") - 1
    if position < 0:
        raise ValueError("start_date precedes the fixed release trading calendar")
    return str(calendar[max(0, int(position) - max(0, lookback_days - 1))])[:10]


def _calendar_until(reader: Any, scope: Any, end_date: str) -> list[str]:
    conn = reader.base_connection(scope)
    rows = conn.query("SELECT date FROM ts_trade_day_calendar WHERE exchange=%s AND is_open=1 AND date <= %s ORDER BY date",
                      ("SSE", end_date))
    return [str(row["date"])[:10] for row in rows]


def provider_price_rows(provider: Any, members: list[str], start_date: str, end_date: str) -> dict[str, list[dict[str, Any]]]:
    """Read RAW prices through the same release-bound Provider as backtests."""
    from quantradar.providers.investment_data.symbols import to_joinquant_symbol

    fields = ["open", "high", "low", "close", "volume", "amount"]
    jq_members = [to_joinquant_symbol(symbol) for symbol in members]
    wide = provider.get_price(jq_members, start_date=start_date, end_date=end_date,
                              frequency="daily", fields=fields)
    result: dict[str, list[dict[str, Any]]] = {}
    for symbol, jq_symbol in zip(members, jq_members):
        frame = wide.xs(jq_symbol, level="security", axis=1) if isinstance(wide.columns, pd.MultiIndex) else wide
        frame = frame.reindex(columns=fields)
        result[symbol] = [
            {**row, "trade_date": index, "unit_contract_version": "joinquant-shares-yuan-v2"}
            for index, row in frame.to_dict(orient="index").items()
        ]
    return result


def lifecycle_universe(dates: pd.DatetimeIndex, members: list[str], lifecycle_rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the eligibility mask from declared membership and release lifecycle facts."""
    mask = pd.DataFrame(False, index=dates, columns=members, dtype=bool)
    by_symbol = {str(row["symbol"]): row for row in lifecycle_rows}
    for symbol in members:
        row = by_symbol.get(symbol)
        if not row or not row.get("list_date"):
            continue
        active = dates >= pd.Timestamp(row["list_date"])
        if row.get("delist_date"):
            active &= dates < pd.Timestamp(row["delist_date"])
        mask.loc[active, symbol] = True
    return mask


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
    from quantradar.config import load_datahub_config
    from quantradar.datahub.reader import ReleaseReader
    scope = ReleaseReader(load_datahub_config()).resolve(release_id)
    calendar = _calendar_until(ReleaseReader(load_datahub_config()), scope, start) if start else []
    calculation_start = calculation_start_from_calendar(calendar, start, max_lookback) if start else ""
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
    from quantradar.bootstrap import release_provider
    from quantradar.config import load_datahub_config
    from quantradar.datahub.reader import ReleaseReader
    from quantradar.datahub.research_inputs import standard_panel
    provider, scope = release_provider(config["release_id"])
    reader = ReleaseReader(load_datahub_config())
    rows = provider_price_rows(provider, config["members"], config.get("calculation_start", config["start_date"]), config["end_date"])
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
    if scope.supplemental_database:
        supplement = reader.supplemental_reader(scope)
        try:
            cap_rows = supplement.market_caps(config["members"], config.get("calculation_start", config["start_date"]), config["end_date"])
            industry_rows = supplement._query(
                "SELECT symbol, industry_code, effective_from, effective_to FROM qr_sw_industry_history "
                "WHERE symbol IN (" + ",".join(["%s"] * len(config["members"])) + ") "
                "AND effective_from <= %s AND (effective_to IS NULL OR effective_to >= %s)",
                (*config["members"], config["end_date"], config.get("calculation_start", config["start_date"])),
            )
        except Exception as exc:
            # A historical release may predate one optional research table.
            # Treat that as an input block; do not convert it to a batch error.
            if exc.__class__.__name__ != "ProgrammingError":
                raise
            cap_rows, industry_rows = {}, []
        cap_frame = pd.DataFrame([
            {"symbol": symbol, "trade_date": row["trade_date"], "cap": row["total_market_cap_cny"]}
            for symbol, values in cap_rows.items() for row in values
        ])
        if not cap_frame.empty:
            fields["cap"] = cap_frame.pivot(index="trade_date", columns="symbol", values="cap").reindex(
                index=fields["close"].index, columns=fields["close"].columns
            )
        from .qualification import qualified_industry_fields
        if industry_rows and qualified_industry_fields(scope.manifest):
            dates = fields["close"].index
            for level, width in (("sector", 2), ("industry", 4), ("subindustry", 6)):
                industry = pd.DataFrame(index=dates, columns=fields["close"].columns, dtype=object)
                for row in industry_rows:
                    active = (dates >= pd.Timestamp(row["effective_from"]))
                    if row.get("effective_to"):
                        active &= dates <= pd.Timestamp(row["effective_to"])
                    industry.loc[active, row["symbol"]] = str(row["industry_code"])[:width]
                fields["indclass." + level] = industry
    # Membership is explicit and intentionally independent of per-day price
    # availability: missing facts must remain visible to qualification.
    lifecycle_rows = []
    if scope.supplemental_database:
        lifecycle_rows = list(reader.supplemental_reader(scope).lifecycles(config["members"]).values())
    fields["universe"] = lifecycle_universe(fields["close"].index, config["members"], lifecycle_rows)
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
            qualification = preflight(set(panel), set(row["fields"]),
                                      panel_dates=panel["open"].index,
                                      requested_dates=requested_dates,
                                      lookback_days=int(row["lookback_days"]), panel=panel)
            if qualification["status"] != "READY":
                config["items"].append({"alpha_id": alpha_id, **qualification})
                update_experiment(batch_id, config=config)
                continue
            config["items"].append({"alpha_id": alpha_id, "status": "READY"})
            item_position = len(config["items"]) - 1
            update_experiment(batch_id, config=config)
            try:
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
                config["items"][item_position] = {"alpha_id": alpha_id, "status": item_status, "calculation": calc_status, "value_artifact": str(value_path), "evaluations": evaluations}
            except Exception as exc:
                config["items"][item_position] = failed_engine_item(alpha_id, exc)
            update_experiment(batch_id, config=config)
        config["status"] = batch_status([str(item["status"]) for item in config["items"]])
        fingerprint = cache_key({
            "release_id": config["release_id"], "base_commit": config["base_commit"],
            "supplemental_commit": config["supplemental_commit"], "members_hash": config["members_hash"],
            "split_dates": config["split_dates"], "alpha_ids": config["alpha_ids"], "horizons": config["horizons"],
            "results": result_summary_items(config["items"]),
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
