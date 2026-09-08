"""Supplementary real-browser recovery checks, using one dedicated local run."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT = Path("docs/acceptance/joinquant-layout")
URL = "http://127.0.0.1:7231/"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.goto(URL)
    page.get_by_label("载入样例").select_option("buyhold")
    page.get_by_label("策略名称").fill("执行中恢复与报告缺失验收")
    page.get_by_label("结束日期", exact=True).fill("2023-01-06")
    page.get_by_label("结束日期", exact=True).press("Enter")
    page.locator(".monaco-editor").click()
    page.keyboard.press("Control+Home")
    page.keyboard.insert_text("import time\ntime.sleep(8)\n")
    with page.expect_response(lambda r: r.url.endswith("/api/backtest/async")) as response:
        page.get_by_role("button", name="运行策略回测", exact=True).click()
    run_id = response.value.json()["run_id"]
    page.get_by_text("回测列表", exact=True).click()
    page.get_by_label("搜索回测").fill(run_id)
    active = page.request.get(URL + f"api/backtest/runs/{run_id}").json()
    assert active["status"] in ("PENDING", "RUNNING"), active["status"]
    page.get_by_role("button", name="恢复源码与配置", exact=True).click()
    expect(page.locator(".run-status")).to_contain_text("回测执行中")
    expect(page.locator(".run-status")).to_contain_text("状态：SUCCESS", timeout=120000)
    page.locator(".returns-chart:visible canvas").wait_for()
    page.screenshot(path=str(OUT / "restore-running-result.png"))
    run = page.request.get(URL + f"api/backtest/runs/{run_id}").json()
    # Deliberately remove ONLY this test run's metrics temporarily; always restore.
    original = Path(run["config"]["run_dir"]) / "metrics.json"
    backup = original.with_suffix(".json.acceptance-backup")
    original.rename(backup)
    try:
        page.get_by_role("button", name="打开完整回测报告 →").click()
        expect(page.locator(".report-content")).to_contain_text("报告不可用")
        expect(page.locator(".report-content")).to_contain_text("metrics.json")
        page.locator(".report-sidebar").get_by_text("报告文件", exact=True).click()
        expect(page.get_by_role("link", name="report.html", exact=True)).to_be_visible()
        page.screenshot(path=str(OUT / "missing-data-artifacts.png"))
        page.locator(".report-sidebar").get_by_text("详细报告", exact=True).click()
        frame = page.frame_locator('iframe[title="BulletTrade 回测报告"]')
        expect(frame.locator("body")).to_contain_text("策略收益", timeout=30000)
    finally:
        backup.rename(original)
    page.get_by_role("button", name="← 返回继续编辑").click()
    page.get_by_role("button", name="打开完整回测报告 →").click()
    page.locator(".report-content .returns-chart canvas").wait_for()
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function("document.querySelector('.report-content .returns-chart canvas').getBoundingClientRect().width < 390")
    page.screenshot(path=str(OUT / "mobile-report.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    (OUT / "edges.json").write_text(json.dumps({"run_id": run_id, "restored_status": active["status"], "completed_status": run["status"], "missing_metrics_error": True, "surviving_artifacts_accessible": True, "metrics_restored": original.exists(), "mobile_report_no_overflow": True}, ensure_ascii=False, indent=2))
    print("RECOVERY_AND_MISSING_REPORT_PASS", run_id)
    browser.close()
