"""统一回测链（BulletTrade WebUI 收口阶段核心）。

严格复用 BulletTrade 原生能力，禁止重实现撮合/账户/订单/成交/调度/指标/报告：
    用户策略源码 → 版本化 strategy.py → InvestmentDataProvider（只读真实数据）
    → bullet_trade.core.engine.create_backtest() → bullet_trade.core.analysis.generate_report()
    → bullet_trade.reporting.generate_cli_report() → runs/<run_id>/ 产物目录

每次成功回测建立独立目录 runs/<run_id>/，至少保存 BulletTrade 原生：
    report.html（详细交互报告：指标+曲线+月度热力图+Trades/Positions/Daily 表）
    standard_report.html（聚宽风格精简报告，generate_cli_report 产出）
    metrics.json（完整 BulletTrade 指标：策略收益/年化/基准/超额/最大回撤/夏普/索提诺/Calmar/胜率/盈亏比/交易天数…）
    daily_records.csv / trades.csv / daily_positions.csv / risk_metrics.csv / annual_returns/monthly_returns/open_counts/instrument_pnl 的 CSV
    backtest.log（日志）
    snapshot.json（QuantRadar 附加审计信息，不替代原生 metrics）

PostgreSQL 只保存 run_id/状态/策略版本/配置(含 run_dir 与报告路径)/完整 BulletTrade metrics/result_hash，
大文件全部留在 runs/<run_id>/ 文件系统，不入库。

除非发现明确 BulletTrade bug，否则不得修改其核心实现。
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

from quantradar.backtest import _FQ_LOCK
from quantradar.audit import collect_audit_env
from quantradar.snapshot import _to_native, build_snapshot_from_results, write_snapshot_json
from quantradar.datahub.maintenance import base_lease

log = logging.getLogger(__name__)


def default_runs_dir() -> str:
    """返回回测产物根目录 runs/（可用 QUANT_RADAR_RUNS_DIR 覆盖）。"""
    env = os.environ.get("QUANT_RADAR_RUNS_DIR")
    if env:
        return os.path.abspath(env)
    # backend/quantradar/backtest_run.py -> 仓库根为 ../../..
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(repo_root, "runs")


def require_report_artifacts(run_dir: str) -> None:
    required = ("report.html", "standard_report.html", "metrics.json", "daily_records.csv", "backtest.log", "strategy.py")
    missing = [name for name in required if not os.path.isfile(os.path.join(run_dir, name)) or os.path.getsize(os.path.join(run_dir, name)) == 0]
    if missing:
        raise ValueError("回测报告产物缺失或为空：" + ", ".join(missing))


def _write_builtin_strategy(path: str, security: str, amount: int) -> None:
    """内置 Buy&Hold 策略文件（对指定标的建仓并持有）。"""
    code = (
        "def initialize(context):\n"
        f"    context.security = '{security}'\n"
        f"    context.amount = {int(amount)}\n"
        "\n"
        "def handle_data(context, data):\n"
        "    if not context.portfolio.positions:\n"
        "        order_target(context.security, context.amount)\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(code)


def run_unified_backtest(
    run_id: str,
    payload: Dict[str, Any],
    runs_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """运行一次真实回测并产出完整 BulletTrade 原生报告产物。

    Args:
        run_id: 运行标识（用于产物目录名与落库主键）。
        payload: {code, security, start_date, end_date, initial_cash, frequency, amount,
                  benchmark, fq, extras, strategy_name}。
        runs_dir: 产物根目录（缺省 default_runs_dir()）。

    Returns:
        {
          run_id, run_dir, report_html, standard_report_html, metrics(BulletTrade 完整指标),
          snapshot(审计附加), result_hash, records_count
        }
    """
    runs_dir = runs_dir or default_runs_dir()
    run_dir = os.path.join(runs_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)

    code = payload.get("code")
    security = payload.get("security") or "600519.XSHG"
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    initial_cash = float(payload.get("initial_cash", 500000))
    frequency = payload.get("frequency", "day")
    amount = int(payload.get("amount", 100))
    benchmark = payload.get("benchmark")
    fq = (payload.get("fq") or "none").lower()
    extras = payload.get("extras") or {}
    strategy_name = payload.get("strategy_name") or "user_strategy"

    if fq not in ("none", "pre", "qfq"):
        raise ValueError(
            f"run_unified_backtest: 不支持的复权方式 fq={fq!r}；"
            f"支持 none / pre / qfq；不支持后复权撮合"
        )

    # 1) 版本化策略文件（用户源码或内置 Buy&Hold）
    strategy_path = os.path.join(run_dir, "strategy.py")
    if code:
        with open(strategy_path, "w", encoding="utf-8") as f:
            f.write(code)
    else:
        _write_builtin_strategy(strategy_path, security, amount)

    log_file = os.path.join(run_dir, "backtest.log")
    _use_real_price = fq != "none"

    from bullet_trade.core.engine import create_backtest
    from bullet_trade.core.analysis import generate_report
    from bullet_trade.reporting import generate_cli_report
    from bullet_trade.core.settings import get_settings, set_option

    from quantradar.bootstrap import bootstrap_data_release, bootstrap_investment_data

    # 2) 复权口径（全局线程安全临界区）+ 激活只读 InvestmentDataProvider + 原生回测
    with _FQ_LOCK, base_lease():
        _prev = get_settings().options.get("use_real_price", False)
        set_option("use_real_price", _use_real_price)
        try:
            release_id = payload.get("release_id")
            try:
                scope = bootstrap_data_release(release_id)
            except FileNotFoundError:
                if release_id is not None:
                    raise
                scope = None
                bootstrap_investment_data(set_active=True, overwrite=True)
            audit_env = collect_audit_env()
            if scope is not None:
                audit_env["data_release"] = {
                    "release_id": scope.release_id,
                    "base_commit": scope.manifest["base_commit"],
                    "supplemental_commit": scope.manifest["supplemental_commit"],
                    "schema_version": scope.manifest["schema_version"],
                    "price_units": scope.manifest.get('metadata', {}).get('price_units', 'legacy-v1'),
                }
                audit_env["dolt_commit"] = scope.manifest["base_commit"]
            try:
                results = create_backtest(
                    strategy_file=strategy_path,
                    start_date=start_date,
                    end_date=end_date,
                    frequency=frequency,
                    initial_cash=initial_cash,
                    benchmark=benchmark,
                    log_file=log_file,
                    extras=extras,
                    use_real_price=_use_real_price,
                )
            except SystemExit as exc:
                raise ValueError(f"策略严格预检拒绝运行：{exc}") from exc
            from bullet_trade.data import get_data_provider
            provider = get_data_provider()
            if hasattr(provider, 'data_usage'):
                audit_env['data_usage'] = provider.data_usage()
        finally:
            set_option("use_real_price", _prev)

    dr = results.get("daily_records")
    if dr is None or getattr(dr, "empty", False) or len(dr) == 0:
        raise ValueError("回测未产出任何交易日记录（检查区间/数据/策略）")
    effective_benchmark = (results.get("meta") or {}).get("benchmark")
    if effective_benchmark and ("benchmark_value" not in dr.columns or dr["benchmark_value"].isna().any()):
        raise ValueError(f"基准 {effective_benchmark} 在回测区间缺少行情，不能生成零收益基准报告；请选择本地已覆盖的基准")

    # 3) BulletTrade 原生报告（report.html + CSV + metrics.json + PNG）
    generate_report(
        results,
        output_dir=run_dir,
        gen_csv=True,
        gen_html=True,
        gen_images=True,
    )

    # 4) 聚宽风格标准化报告（standard_report.html）
    standard_report_html = os.path.join(run_dir, "standard_report.html")
    generate_cli_report(
        input_dir=run_dir,
        output_path=standard_report_html,
        fmt="html",
        title=strategy_name,
    )
    require_report_artifacts(run_dir)

    # 5) QuantRadar 附加审计快照（不替代 BulletTrade 原生 metrics）
    with open(strategy_path, encoding="utf-8") as source_file:
        strategy_source = source_file.read()
    snapshot = build_snapshot_from_results(
        results,
        strategy_source=strategy_source,
        config={
            "security": security if not code else None,
            "initial_cash": initial_cash,
            "start_date": start_date,
            "end_date": end_date,
            "frequency": frequency,
            "amount": amount,
            "benchmark": benchmark,
            "fq": fq,
            "extras": extras,
            "strategy_name": strategy_name,
        },
        fq=fq,
        audit_env=audit_env,
    )
    snapshot = write_snapshot_json(os.path.join(run_dir, "snapshot.json"), snapshot)

    metrics = results.get("metrics") or {}
    dr = results.get("daily_records")
    records_count = len(dr) if (dr is not None and not getattr(dr, "empty", False)) else 0
    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "report_html": os.path.join(run_dir, "report.html"),
        "standard_report_html": standard_report_html,
        "metrics": _to_native(metrics),
        "snapshot": snapshot,
        "result_hash": snapshot.get("result_hash"),
        "records_count": records_count,
    }


def make_run_id() -> str:
    """生成 run_id（与 worker 命名一致，便于直接复用）。"""
    return "run_" + uuid.uuid4().hex
