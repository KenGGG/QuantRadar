from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .models import json_safe


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(json_safe(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    extras = sorted({key for row in rows for key in row} - set(fieldnames))
    fieldnames.extend(extras)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def _price_markdown(bundle: dict[str, Any], gates: dict[str, Any]) -> str:
    rows = bundle["prices"]["rows"]
    passed = sum(row.get("status") == "PASS" for row in rows)
    coverage = {row["dataset"]: row for row in bundle["schema"]["coverage"]}
    return "\n".join(
        [
            "# Kronos Goal 0 价格语义审计",
            "",
            f"- 价格样本：{len(rows)}；通过：{passed}；失败：{len(rows) - passed}",
            f"- 价格覆盖：{coverage.get('price', {}).get('min_date')} ～ "
            f"{coverage.get('price', {}).get('max_date')}",
            f"- 价格语义门禁：{gates['gates']['price_semantics']['status']}",
            "",
            "## 唯一价格契约",
            "",
            "- `fq=none`：`final_a_stock_eod_price` 原始 OHLC。",
            "- `fq=post/hfq`：原始 OHLC × (`adjclose / close`)。",
            "- `fq=pre/qfq`：原始 OHLC × 当日因子 / 显式参考日因子。",
            "- Kronos 后续输入必须使用 `pre_factor_ref_date=signal_date`。",
            "- `volume` 与 `amount` 不随价格复权。",
            "- BulletTrade 成交与账户估值使用原始价；连续研究特征使用显式参考日的 qfq。",
            "",
            "## 已知限制",
            "",
            "- 公司行为表不存在，`preclose/adjfactor` 只能作为事件代理证据。",
            "- ST、tradestatus、涨跌停及股票主数据的独立覆盖以前沿报告为准。",
            "- 审计完成不等于正式回测或实盘数据门禁通过。",
            "",
        ]
    )


def _data_contract(bundle: dict[str, Any]) -> dict[str, Any]:
    coverage = {row["dataset"]: row for row in bundle["schema"]["coverage"]}
    return {
        "version": "kronos-data-contract-v1",
        "price_semantics": bundle["prices"]["contract"],
        "fields": {
            "raw_open/high/low/close": "final_a_stock_eod_price.open/high/low/close",
            "adjusted_open/high/low/close": "derived from raw OHLC and final adjclose/close factor",
            "adj_factor": "final_a_stock_eod_price.adjclose / close",
            "volume": "final_a_stock_eod_price.volume (unadjusted)",
            "amount": "final_a_stock_eod_price.amount (unadjusted)",
            "pre_close": "final_a_stock_limit.pre_close; bao preclose only through its own coverage",
            "up_limit/down_limit": "final_a_stock_limit.up_limit/down_limit",
            "corporate_action": "bao preclose/adjfactor proxy only; authoritative type unavailable",
            "st": "bao_a_stock_eod_info.is_st",
            "tradestatus": "bao_a_stock_eod_info.tradestatus",
        },
        "coverage": coverage,
        "accounting": {
            "trade_and_valuation_price": "raw OHLC",
            "continuous_research_price": "qfq with explicit signal-date reference",
            "corporate_action_accounting": "PARTIAL: event type/share/cash facts unavailable",
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish_audit_reports(
    bundle: dict[str, Any],
    gates: dict[str, Any],
    *,
    output_dir: str | Path,
    start_commit: str,
    end_commit: str,
    generated_at,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    backup = output.with_name(f".{output.name}.previous")
    try:
        _write_csv(stage / "price_semantics.csv", bundle["prices"]["rows"])
        (stage / "price_semantics.md").write_text(
            _price_markdown(bundle, gates), encoding="utf-8"
        )
        _write_csv(stage / "corporate_actions.csv", bundle["actions"]["rows"])
        _write_csv(stage / "pit_universe_checks.csv", bundle["universe"]["rows"])
        _write_csv(stage / "coverage.csv", bundle["schema"]["coverage"])
        _write_json(
            stage / "schema.json",
            {
                "schemas": bundle["schema"]["schemas"],
                "table_summaries": bundle["schema"]["table_summaries"],
            },
        )
        _write_json(stage / "data_contract.json", _data_contract(bundle))
        _write_json(stage / "data_gate.json", gates)
        artifact_names = sorted(path.name for path in stage.iterdir())
        manifest = {
            "goal": "Goal 0 - data fact audit",
            "completion_marker": "KRONOS_DATA_CONTRACT_AUDIT_COMPLETE",
            "generated_at": generated_at,
            "run_start_commit": start_commit,
            "run_end_commit": end_commit,
            "counts": {
                "price_samples": len(bundle["prices"]["rows"]),
                "action_events": len(bundle["actions"]["rows"]),
                "pit_weeks": len(bundle["universe"]["rows"]),
            },
            "content_hashes": {name: _sha256(stage / name) for name in artifact_names},
        }
        _write_json(stage / "audit_manifest.json", manifest)
        if backup.exists():
            shutil.rmtree(backup)
        if output.exists():
            os.replace(output, backup)
        os.replace(stage, output)
        if backup.exists():
            shutil.rmtree(backup)
        return manifest
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        if backup.exists() and not output.exists():
            os.replace(backup, output)
        raise

