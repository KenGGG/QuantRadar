"""React 研究工作台验收（Closing Phase 3：WEB_WORKBENCH_PASS）。

仅依赖后端 /api/* 真实接口与已构建产物 frontend/dist，无 mock：
  - frontend/dist/index.html 已构建且含中文标题（GET / 托管）。
  - FastAPI GET / 返回 200 且含「量子雷达」（Vite 构建产物被托管）。
  - /api/backtest 返回 WebUI 所需明细：daily_records / trades / positions / metrics / environment / result_hash。
  - /api/health 返回审计环境（供数据状态面板）。
  - /api/backtest/async -> run_id；/api/backtest/runs/{id} 可查（异步链路，PG 不可用时回退同步校验）。
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

frontend_dist = os.path.join(
    os.path.dirname(__file__), "..", "..", "frontend", "dist", "index.html"
)

SECURITY = "600519.XSHG"
START = "2023-01-03"
END = "2023-03-31"
CASH = 500000


def test_frontend_build_exists():
    """前端必须已构建（Vite 产物）。未构建则视为未完成（不 skip，属验收硬性条件）。"""
    assert os.path.exists(frontend_dist), (
        "frontend/dist/index.html 不存在：请 cd frontend && npm install && npm run build"
    )
    with open(frontend_dist, "r", encoding="utf-8") as f:
        html = f.read()
    assert "量子雷达" in html, "构建产物缺少中文标题，GET / 冒烟断言会失败"


def test_web_entry_served():
    from quantradar.api.app import app

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200, f"GET / 失败：{r.status_code}"
    assert "量子雷达" in r.text, "GET / 未托管中文工作台"


@pytest.mark.requires_dolt
def test_health_has_audit_env():
    from quantradar.api.app import app

    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body.get("provider") == "investment_data"
    env = body.get("environment") or {}
    assert env.get("dolt_commit"), "health 未携带 dolt_commit"
    assert env.get("schema_hash"), "health 未携带 schema_hash"


@pytest.mark.requires_dolt
def test_backtest_response_has_webui_details():
    from quantradar.api.app import app

    client = TestClient(app)
    r = client.post(
        "/api/backtest",
        json={"security": SECURITY, "start_date": START, "end_date": END, "initial_cash": CASH},
    )
    assert r.status_code == 200, f"回测失败：{r.text}"
    body = r.json()
    snap = body["snapshot"]
    # 图表/表格所需明细
    assert isinstance(snap.get("daily_records"), list) and len(snap["daily_records"]) > 0
    assert isinstance(snap.get("trades"), list)
    assert isinstance(snap.get("positions"), list)
    # 审计/指标
    assert snap.get("metrics") and snap["metrics"].get("final_total_value") is not None
    assert snap.get("environment") and snap["environment"].get("dolt_commit")
    assert snap.get("result_hash")


@pytest.mark.requires_dolt
def test_async_backtest_runs_and_queryable():
    """异步链路：提交 -> run_id -> 轮询 -> 结果可查。需 PostgreSQL（否则 skip）。"""
    pg_url = os.environ.get("QUANT_RADAR_PG_URL")
    if not pg_url:
        pytest.skip("QUANT_RADAR_PG_URL 未设置：跳过异步链路（同步明细已覆盖）")

    from quantradar.api.app import app
    from quantradar.worker import get_worker

    client = TestClient(app)
    r = client.post(
        "/api/backtest/async",
        json={"security": SECURITY, "start_date": START, "end_date": END, "initial_cash": CASH},
    )
    assert r.status_code == 200, f"异步提交失败：{r.text}"
    run_id = r.json()["run_id"]

    # 等待后台线程完成（Worker 内建 join，超时 240s）
    get_worker().wait(run_id, timeout=240)

    rr = client.get(f"/api/backtest/runs/{run_id}")
    assert rr.status_code == 200
    rec = rr.json()
    assert rec["status"] == "SUCCESS", rec.get("error")
    assert rec["snapshot"] and rec["snapshot"].get("result_hash")

    # 产物清单 + 单文件查看/下载端点（条件② artifact 文件查看/下载）
    arts = client.get(f"/api/backtest/runs/{run_id}/artifacts")
    assert arts.status_code == 200
    names = [a["name"] for a in arts.json()["artifacts"]]
    assert "snapshot.json" in names, "产物清单缺少 snapshot.json"

    snap_file = client.get(f"/api/backtest/runs/{run_id}/artifacts/snapshot.json")
    assert snap_file.status_code == 200
    assert snap_file.headers["content-type"].startswith("application/json")
    assert "result_hash" in snap_file.text, "单文件端点未正确返回 snapshot.json 内容"

    # 目录穿越防护
    trav = client.get(
        f"/api/backtest/runs/{run_id}/artifacts/{__import__('urllib.parse', fromlist=['quote']).quote('..%2F..%2Fetc%2Fpasswd')}"
    )
    assert trav.status_code in (400, 404), "目录穿越未被拦截"

    # 报告 iframe 内联展示（条件① Report inline）：full / standard 两种都必须内联，
    # 不应以附件下载（Content-Disposition: inline）。
    for which in ("full", "standard"):
        rpt = client.get(f"/api/backtest/runs/{run_id}/report", params={"which": which})
        assert rpt.status_code == 200, f"/report?which={which} 失败：{rpt.status_code}"
        assert rpt.headers["content-type"].startswith("text/html"), (
            f"/report?which={which} content-type 非 text/html：{rpt.headers.get('content-type')}"
        )
        cd = rpt.headers.get("content-disposition", "")
        assert "inline" in cd.lower(), (
            f"/report?which={which} 未内联（应 Content-Disposition: inline，实为 {cd!r}）"
        )


# ----------------------------------------------------------------------------
# Worker 重启恢复（最终封版 #83 RUNNING+PENDING / #84 fq 一致性）
# ----------------------------------------------------------------------------

import datetime
import hashlib
import uuid

# 内置 Buy&Hold 策略（与 backtest_run._write_builtin_strategy 等价，供恢复测试直接落库）
_BUYHOLD_CODE = (
    "def initialize(context):\n"
    "    context.security = '600519.XSHG'\n"
    "    context.amount = 100\n"
    "\n"
    "def handle_data(context, data):\n"
    "    if not context.portfolio.positions:\n"
    "        order_target(context.security, context.amount)\n"
)


def _cleanup_orphan_runs():
    """清理本测试创建前库中遗留的 RUNNING/PENDING 运行（模拟进程重启前的孤儿），

    避免 recover() 扫描到历史会话遗留任务而污染本测试断言（recover 本就负责找回全部）。
    """
    from quantradar.storage import list_runs_by_status, update_run

    for rec in list_runs_by_status(["RUNNING", "PENDING"]):
        update_run(
            rec["run_id"],
            status="FAILED",
            error="测试前清理遗留 orphan（非本测试创建）",
        )


def _recover_run_config(run_id: str, fq: str, strategy_id: int) -> Dict[str, Any]:
    """复刻 worker.submit 落库的 config（供直接构造一条「进程崩溃遗留」运行）。"""
    from quantradar.backtest_run import default_runs_dir

    code = _BUYHOLD_CODE
    h = hashlib.sha256(code.encode("utf-8")).hexdigest()
    run_dir = os.path.join(default_runs_dir(), run_id)
    return {
        "security": "600519.XSHG",
        "start_date": "2023-01-03",
        "end_date": "2023-02-10",
        "initial_cash": 500000,
        "frequency": "day",
        "amount": 100,
        "benchmark": "000300.XSHG",
        "fq": fq,
        "extras": {},
        "has_code": True,
        "strategy_name": "recover_test",
        "strategy_id": strategy_id,
        "strategy_hash": h,
        "run_dir": run_dir,
        "report_html": os.path.join(run_dir, "report.html"),
        "standard_report_html": os.path.join(run_dir, "standard_report.html"),
        "strategy_source": code,
    }


def test_worker_recover_pg_unavailable_does_not_block():
    """#83 PostgreSQL 暂不可用时 recover 返回 0，且 _recovered 不置位（允许未来重试）。

    纯逻辑测试，不依赖 Dolt/PG，CI 也运行。
    """
    from quantradar import worker as wmod
    from quantradar.worker import BacktestWorker

    bw = BacktestWorker()

    def _boom(*_a, **_k):
        raise RuntimeError("PostgreSQL 暂不可用（模拟瞬时故障）")

    real = wmod.list_runs_by_status
    wmod.list_runs_by_status = _boom  # type: ignore[assignment]
    try:
        n = bw.recover()
    finally:
        wmod.list_runs_by_status = real  # 还原，避免影响其它测试
    assert n == 0, f"PG 不可用时 recover 应返回 0，实为 {n}"
    assert bw._recovered is False, "PG 不可用后 _recovered 不应置位（否则永久阻断未来恢复）"


@pytest.mark.requires_dolt
def test_worker_restart_recovery_runs_and_pending():
    """#83 进程崩溃遗留的 RUNNING 与 PENDING 都必须被找回并重跑。"""
    if not os.environ.get("QUANT_RADAR_PG_URL"):
        pytest.skip("QUANT_RADAR_PG_URL 未设置：跳过 Worker 重启恢复（RUNNING+PENDING）测试")

    from quantradar.storage import create_run, get_run, save_strategy, update_run
    from quantradar.worker import BacktestWorker

    _cleanup_orphan_runs()

    sid = save_strategy(
        name="recover_rp",
        source=_BUYHOLD_CODE,
        strategy_hash=hashlib.sha256(_BUYHOLD_CODE.encode()).hexdigest(),
    ).id

    def _mk(status: str) -> str:
        rid = "run_" + uuid.uuid4().hex
        create_run(rid, _recover_run_config(rid, "none", sid), strategy_id=sid)
        update_run(
            rid,
            status=status,
            started_at=datetime.datetime.now() if status == "RUNNING" else None,
        )
        return rid

    rid_running = _mk("RUNNING")
    rid_pending = _mk("PENDING")

    # 模拟重启：全新 Worker 实例（_recovered=False），进程内存队列已丢失
    bw = BacktestWorker()
    n = bw.recover()
    assert n == 2, f"recover 应找回 2 条（RUNNING+PENDING），实为 {n}"

    bw.wait(rid_running, timeout=240)
    bw.wait(rid_pending, timeout=240)

    rec_r = get_run(rid_running)
    rec_p = get_run(rid_pending)
    assert rec_r["status"] == "SUCCESS", rec_r.get("error")
    assert rec_p["status"] == "SUCCESS", rec_p.get("error")


@pytest.mark.requires_dolt
@pytest.mark.parametrize("fq", ["none", "pre", "qfq", "post", "hfq"])
def test_worker_restart_recovery_preserves_fq(fq, monkeypatch):
    """#84 Worker 重启恢复后，真实重跑的任务仍使用原始 fq 复权口径（覆盖全部 5 种）。

    验证「重跑时真正使用的 payload.fq == 原始 fq」「落库 config.fq 不变」「审计
    snapshot.config.fq 不变」，而非仅字段存在。
    """
    if not os.environ.get("QUANT_RADAR_PG_URL"):
        pytest.skip("QUANT_RADAR_PG_URL 未设置：跳过 fq 恢复一致性测试")

    from quantradar import worker as wmod
    from quantradar.storage import create_run, get_run, save_strategy, update_run
    from quantradar.worker import BacktestWorker

    _cleanup_orphan_runs()

    # 捕获「恢复后重跑」真实使用的 payload.fq（按 run_id 记录，避免历史 orphan 运行污染）
    captured: Dict[str, Any] = {}
    real_backtest = wmod.run_unified_backtest

    def _spy(run_id, payload, runs_dir=None):
        captured[run_id] = payload.get("fq")
        return real_backtest(run_id, payload, runs_dir)

    monkeypatch.setattr(wmod, "run_unified_backtest", _spy)

    sid = save_strategy(
        name="fq_recover",
        source=_BUYHOLD_CODE,
        strategy_hash=hashlib.sha256(_BUYHOLD_CODE.encode()).hexdigest(),
    ).id
    rid = "run_" + uuid.uuid4().hex
    create_run(rid, _recover_run_config(rid, fq, sid), strategy_id=sid)
    # 模拟崩溃时处于 RUNNING（线程已中断未真正完成）
    update_run(rid, status="RUNNING", started_at=datetime.datetime.now())

    bw = BacktestWorker()
    n = bw.recover()
    assert n == 1, f"recover 应找回 1 条 RUNNING，实为 {n}"

    bw.wait(rid, timeout=240)
    rec = get_run(rid)
    assert rec["status"] == "SUCCESS", rec.get("error")
    # 1) 重跑时真正使用的 payload.fq 与原始一致（关键：非仅字段存在）
    assert captured.get(rid) == fq, f"恢复后重跑 payload.fq 丢失：{captured.get(rid)!r}"
    # 2) 落库 config.fq 不变
    assert rec["config"]["fq"] == fq, f"恢复后 config.fq 丢失：{rec['config'].get('fq')!r}"
    # 3) 审计 snapshot.config.fq 不变
    snap = rec.get("snapshot") or {}
    assert snap.get("config", {}).get("fq") == fq, f"恢复后 snapshot.config.fq 丢失：{snap}"


@pytest.mark.requires_dolt
def test_worker_restart_recovery_pending_preserves_fq(monkeypatch):
    """#84 补充：PENDING（尚未出队）恢复后 fq 同样保持一致（以 pre 为例）。"""
    if not os.environ.get("QUANT_RADAR_PG_URL"):
        pytest.skip("QUANT_RADAR_PG_URL 未设置：跳过 PENDING fq 恢复一致性测试")

    from quantradar import worker as wmod
    from quantradar.storage import create_run, get_run, save_strategy, update_run
    from quantradar.worker import BacktestWorker

    _cleanup_orphan_runs()

    captured: Dict[str, Any] = {}
    real_backtest = wmod.run_unified_backtest

    def _spy(run_id, payload, runs_dir=None):
        captured[run_id] = payload.get("fq")
        return real_backtest(run_id, payload, runs_dir)

    monkeypatch.setattr(wmod, "run_unified_backtest", _spy)

    sid = save_strategy(
        name="fq_recover_pending",
        source=_BUYHOLD_CODE,
        strategy_hash=hashlib.sha256(_BUYHOLD_CODE.encode()).hexdigest(),
    ).id
    rid = "run_" + uuid.uuid4().hex
    fq = "pre"
    create_run(rid, _recover_run_config(rid, fq, sid), strategy_id=sid)
    # 模拟「已落库但尚未出队」：保持 PENDING
    update_run(rid, status="PENDING")

    bw = BacktestWorker()
    n = bw.recover()
    assert n == 1, f"recover 应找回 1 条 PENDING，实为 {n}"

    bw.wait(rid, timeout=240)
    rec = get_run(rid)
    assert rec["status"] == "SUCCESS", rec.get("error")
    assert captured.get(rid) == fq, f"恢复后重跑 payload.fq 丢失：{captured.get(rid)!r}"
    assert rec["config"]["fq"] == fq, f"恢复后 config.fq 丢失：{rec['config'].get('fq')!r}"
    snap = rec.get("snapshot") or {}
    assert snap.get("config", {}).get("fq") == fq, f"恢复后 snapshot.config.fq 丢失：{snap}"
