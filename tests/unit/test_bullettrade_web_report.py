"""BulletTrade WebUI 收口验收（BULLETTRADE_WEB_REPORT_PASS 前置自动化）。

覆盖 /goal 七节验收的「报告 API + Web 页面 + 真实策略端到端」：

  A) 统一回测链（真实策略端到端，仅依赖 Dolt，不依赖 PG）：
     用户提交的 JoinQuant 兼容策略源码 → run_unified_backtest → BulletTrade 原生
     report.html / standard_report.html / metrics.json / 各类 CSV / PNG / backtest.log /
     snapshot.json 全部落地 runs/<run_id>/；metrics.json 覆盖目标全部指标
     （策略收益/年化/基准/超额/最大回撤/区间/夏普/索提诺/Calmar/胜率/盈亏比/交易天数）。
     关键原则：禁止前端重算——指标完全来自 BulletTrade 原生报告。

  B) 报告 API（依赖 Dolt + 测试 PG，缺失则 skip）：
     /api/backtest/runs/{id}/report?which=full|standard 返回 200 HTML 且含关键指标；
     /api/backtest/runs/{id}/artifacts 列出全部产物；历史 Run 可再次打开同一报告（幂等）。

  C) Web 页面（仅依赖前端构建产物）：
     frontend/dist 已构建；SPA 托管；ReportPage 已进入构建产物（非死代码），
     且其依赖的报告/产物 API 契约（getRunReportUrl/standard_report/QuantRadar 审计）在场。

全程禁止 mock；价格/回测均来自真实 investment_data。
"""

from __future__ import annotations

import json
import os

import pytest

pytestmark = pytest.mark.requires_dolt

# 一个 JoinQuant 兼容的真实用户策略（Buy & Hold：建仓后持有）
JOINQUANT_STRATEGY = (
    "def initialize(context):\n"
    "    context.security = '600519.XSHG'\n"
    "    context.amount = 100\n"
    "\n"
    "def handle_data(context, data):\n"
    "    # 首个交易日建仓并持有（JoinQuant 风格：order_target + context.portfolio）\n"
    "    if not context.portfolio.positions:\n"
    "        order_target(context.security, context.amount)\n"
)

SECURITY = "600519.XSHG"
START = "2023-01-03"
END = "2023-03-31"
CASH = 500000
BENCHMARK = "000300.XSHG"

# /goal 目标要求 BulletTrade 原生指标覆盖（metrics.json 中文键）
REQUIRED_METRIC_KEYS = [
    "策略收益", "策略年化收益", "基准收益", "累计超额收益",
    "最大回撤", "最大回撤区间", "夏普比率", "索提诺比率",
    "Calmar比率", "胜率", "盈亏比", "交易天数",
]

# report.html / standard_report.html 中应出现的关键指标词
REPORT_MARKERS = ["策略收益", "年化", "基准", "超额", "最大回撤", "夏普", "索提诺", "Calmar", "胜率", "盈亏比", "交易天数"]
STANDARD_REPORT_MARKERS = ["策略收益", "年化", "基准", "超额", "最大回撤", "夏普", "索提诺", "Calmar", "胜率", "盈亏比", "交易天数", "净值", "回撤", "月度", "收益曲线"]


# --------------------------- 测试 PG（_test 库）解析 ---------------------------
def _resolve_test_pg_url() -> "str | None":
    """解析可用的测试 PG 连接串（库名须含 _test，供 storage.drop_all 守护）。

    优先 QUANT_RADAR_TEST_PG_URL；否则从 QUANT_RADAR_PG_URL 派生一个 _test 库
    （替换库名为 quantradar_test）并校验连通性。不硬编码凭证——完全来自运行环境。
    """
    explicit = os.environ.get("QUANT_RADAR_TEST_PG_URL")
    if explicit:
        return explicit
    base = os.environ.get("QUANT_RADAR_PG_URL")
    if not base:
        return None
    try:
        prefix = base.rsplit("/", 1)[0]
        candidate = prefix + "/quantradar_test"
        from sqlalchemy import create_engine, text

        e = create_engine(candidate)
        with e.connect() as c:
            c.execute(text("SELECT 1"))
        return candidate
    except Exception:
        return None


TEST_PG_URL = _resolve_test_pg_url()
if TEST_PG_URL:
    # 让 storage._pg_url() 优先指向测试库（避免误写生产库）；同时使既有
    # test_persist_worker.py 在同会话中也走测试库。
    os.environ.setdefault("QUANT_RADAR_TEST_PG_URL", TEST_PG_URL)


# --------------------------- A) 统一回测链：真实策略端到端 ---------------------------

def _run_unified_in_tmp(tmp_path):
    from quantradar.backtest_run import make_run_id, run_unified_backtest

    return run_unified_backtest(
        make_run_id(),
        {
            "code": JOINQUANT_STRATEGY,
            "start_date": START,
            "end_date": END,
            "initial_cash": CASH,
            "frequency": "day",
            "benchmark": BENCHMARK,
            "fq": "none",
            "strategy_name": "验收BuyHold",
        },
        runs_dir=str(tmp_path),
    )


def test_unified_backtest_produces_full_bulletrade_artifacts(tmp_path):
    """真实策略端到端：产出 BulletTrade 原生报告 + 完整指标 + CSV/日志/snapshot。"""
    info = _run_unified_in_tmp(tmp_path)
    run_dir = info["run_dir"]

    # 1) 必须落地的产物
    required_files = [
        "report.html", "standard_report.html", "metrics.json",
        "daily_records.csv", "trades.csv", "daily_positions.csv",
        "risk_metrics.csv", "backtest.log", "snapshot.json", "strategy.py",
    ]
    for name in required_files:
        p = os.path.join(run_dir, name)
        assert os.path.isfile(p), f"缺失产物：{name}"
        assert os.path.getsize(p) > 0, f"产物为空：{name}"

    # 2) metrics.json 覆盖目标全部指标（禁止前端重算的根基）
    #    BulletTrade 写盘结构为 {"generated_at", "metrics": {...}, "meta"}，指标在 "metrics" 下
    with open(os.path.join(run_dir, "metrics.json"), encoding="utf-8") as f:
        raw = json.load(f)
    metrics = raw.get("metrics", raw)
    missing = [k for k in REQUIRED_METRIC_KEYS if k not in metrics]
    assert not missing, f"metrics.json 缺指标：{missing}"
    # 关键指标应为数值且非空
    for k in ("策略收益", "夏普比率", "最大回撤", "交易天数", "基准收益", "累计超额收益"):
        assert metrics.get(k) is not None, f"指标 {k} 为空"

    # 3) 原生报告 HTML 含关键指标词（report.html + standard_report.html）
    html = open(info["report_html"], encoding="utf-8").read()
    for marker in REPORT_MARKERS:
        assert marker in html, f"report.html 缺少指标词：{marker}"
    assert os.path.getsize(info["report_html"]) > 100_000, "report.html 过小，疑似非完整报告"

    shtml = open(info["standard_report_html"], encoding="utf-8").read()
    for marker in STANDARD_REPORT_MARKERS:
        assert marker in shtml, f"standard_report.html 缺少指标词：{marker}"

    # 4) 附加审计 snapshot.json 含 QuantRadar 审计字段（不替代原生 metrics）
    with open(os.path.join(run_dir, "snapshot.json"), encoding="utf-8") as f:
        snap = json.load(f)
    assert snap["result_hash"], "snapshot 缺 result_hash"
    assert snap["config_hash"], "snapshot 缺 config_hash"
    assert snap["strategy_hash"], "snapshot 缺 strategy_hash"
    env = snap["environment"]
    for k in ("provider", "provider_version", "dolt_commit", "schema_hash",
              "bullettrade_commit", "quantradar_commit"):
        assert k in env and env[k] is not None, f"snapshot.environment 缺 {k}"

    # 5) 返回结构一致性（供 WebUI / API 消费）
    assert info["records_count"] > 0
    assert info["result_hash"] == snap["result_hash"]


# --------------------------- B) 报告 API（依赖测试 PG） ---------------------------

def _ensure_test_pg():
    if not TEST_PG_URL:
        pytest.skip("需要测试 PG（_test 库）：跳过报告 API 端到端（可通过 QUANT_RADAR_TEST_PG_URL 启用）")


def test_report_and_artifacts_endpoints_e2e(tmp_path, monkeypatch):
    """异步提交真实策略 → 落库 → /report 与 /artifacts 可直接服务 BulletTrade 原生产物。"""
    _ensure_test_pg()
    # 产物写入临时 runs 根目录，避免污染仓库 runs/
    monkeypatch.setenv("QUANT_RADAR_RUNS_DIR", str(tmp_path))

    from fastapi.testclient import TestClient

    from quantradar.api.app import app
    from quantradar.worker import get_worker

    client = TestClient(app)
    resp = client.post(
        "/api/backtest/async",
        json={
            "code": JOINQUANT_STRATEGY,
            "start_date": START,
            "end_date": END,
            "initial_cash": CASH,
            "benchmark": BENCHMARK,
            "fq": "none",
            "strategy_name": "验收BuyHold",
        },
    )
    assert resp.status_code == 200, f"异步提交失败：{resp.text}"
    run_id = resp.json()["run_id"]

    # 等待后台执行完成
    get_worker().wait(run_id, timeout=300)

    rec = client.get(f"/api/backtest/runs/{run_id}")
    assert rec.status_code == 200
    body = rec.json()
    assert body["status"] == "SUCCESS", body.get("error")
    assert body["snapshot"] and body["snapshot"].get("result_hash")
    assert body["metrics"] and body["metrics"].get("策略收益") is not None
    # config 含产物路径与策略参数（ReportPage 依赖）
    cfg = body["config"] or {}
    assert cfg.get("run_dir") and os.path.isdir(cfg["run_dir"])
    assert cfg.get("fq") == "none"

    # 1) 详细报告 full
    r_full = client.get(f"/api/backtest/runs/{run_id}/report", params={"which": "full"})
    assert r_full.status_code == 200, r_full.text
    assert r_full.headers["content-type"].startswith("text/html")
    full_text = r_full.text
    for marker in ("策略收益", "夏普", "最大回撤"):
        assert marker in full_text, f"full 报告缺 {marker}"

    # 2) 聚宽风格标准报告 standard
    r_std = client.get(f"/api/backtest/runs/{run_id}/report", params={"which": "standard"})
    assert r_std.status_code == 200, r_std.text
    assert r_std.headers["content-type"].startswith("text/html")
    std_text = r_std.text
    for marker in ("净值", "月度", "收益曲线"):
        assert marker in std_text, f"standard 报告缺 {marker}"

    # 3) 历史 Run 再次打开同一报告（幂等）
    r_again = client.get(f"/api/backtest/runs/{run_id}/report", params={"which": "full"})
    assert r_again.status_code == 200 and len(r_again.text) > 100_000

    # 4) 产物清单
    r_art = client.get(f"/api/backtest/runs/{run_id}/artifacts")
    assert r_art.status_code == 200, r_art.text
    art = r_art.json()
    names = {a["name"] for a in art["artifacts"]}
    assert "report.html" in names and "standard_report.html" in names
    assert "metrics.json" in names and "daily_records.csv" in names
    assert "trades.csv" in names and "backtest.log" in names
    # 两份报告标记为 is_report=True，且提供可访问 URL
    reports = [a for a in art["artifacts"] if a["is_report"]]
    assert len(reports) == 2
    assert art["report_url"].endswith("which=full")
    assert art["standard_report_url"].endswith("which=standard")


def test_report_endpoint_unknown_run_404():
    """不存在的 run 返回 404（不抛 500）。"""
    _ensure_test_pg()
    from fastapi.testclient import TestClient

    from quantradar.api.app import app

    client = TestClient(app)
    r = client.get("/api/backtest/runs/run_does_not_exist/report", params={"which": "full"})
    assert r.status_code == 404


# --------------------------- C) Web 页面（仅依赖前端构建） ---------------------------

def _dist_index():
    return os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist", "index.html")


def _dist_js_bundles():
    assets = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist", "assets")
    if not os.path.isdir(assets):
        return []
    return [os.path.join(assets, f) for f in os.listdir(assets) if f.endswith(".js")]


def test_frontend_build_exists_for_report():
    """前端必须已构建（Vite 产物），含中文标题。"""
    assert os.path.exists(_dist_index()), (
        "frontend/dist/index.html 不存在：请 cd frontend && npm install && npm run build"
    )
    html = open(_dist_index(), encoding="utf-8").read()
    assert "量子雷达" in html, "构建产物缺少中文标题"


def test_report_page_compiled_into_bundle():
    """ReportPage 已编译进 SPA 产物（非死代码），且依赖的报告/审计 API 契约在场。"""
    bundles = _dist_js_bundles()
    assert bundles, "找不到前端 JS bundle：请先构建 frontend"
    combined = "\n".join(open(b, encoding="utf-8", errors="ignore").read() for b in bundles)
    # ReportPage 标题与审计面板标题
    assert "回测报告" in combined, "构建产物缺少 ReportPage 标题「回测报告」"
    assert "QuantRadar 审计" in combined, "构建产物缺少 ReportPage 审计面板「QuantRadar 审计」"
    # 报告/产物 API 契约（api.ts 生成）
    assert "standard_report" in combined, "构建产物缺少报告 URL 契约（getRunReportUrl/standard_report）"
    assert "/api/backtest/runs/" in combined, "构建产物缺少 runs API 路径"


def test_spa_serves_report_route():
    """GET / 托管 SPA；客户端路由 /report 由前端接管（服务端回退 index.html）。"""
    from fastapi.testclient import TestClient

    from quantradar.api.app import app

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200, f"GET / 失败：{r.status_code}"
    assert "量子雷达" in r.text
    # 带前缀的 SPA 路由回退到 index.html（非 404）
    r2 = client.get("/runs/some-id")
    assert r2.status_code == 200 and "量子雷达" in r2.text
