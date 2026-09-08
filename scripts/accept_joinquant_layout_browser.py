"""Real deployed Chromium acceptance for the JoinQuant layout; no mocked runs."""
import csv
import json
import subprocess
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

OUT = Path("docs/acceptance/joinquant-layout")
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:7231/"


def section(page, label):
    page.locator(".report-sidebar").get_by_text(label, exact=True).click()


def fill_date(page, label, value):
    field = page.get_by_label(label, exact=True)
    field.fill(value)
    field.press("Enter")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    records = []
    for key, cash, start, end, benchmark in [
        ("buyhold", 500000, "2023-01-03", "2023-03-31", "000300.XSHG"),
        ("dma", 600000, "2023-02-01", "2023-02-28", "600519.XSHG"),
        ("rebalance", 900000, "2023-01-03", "2023-01-31", "000300.XSHG"),
    ]:
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(URL)
        page.get_by_label("载入样例").select_option(key)
        name = page.get_by_label("策略名称").input_value() + " · 聚宽布局验收"
        page.get_by_label("策略名称").fill(name)
        page.locator(".monaco-editor").click()
        page.keyboard.press("Control+End")
        page.keyboard.press("Enter")
        page.keyboard.type("# joinquant layout browser edit")
        with page.expect_response(lambda r: r.url.endswith("/api/strategies") and r.request.method == "POST") as response:
            page.get_by_role("button", name="保存策略版本", exact=True).click()
        saved = response.value.json()
        assert response.value.ok and "# joinquant layout browser edit" in saved["source"]
        page.reload()
        page.get_by_label("打开策略版本").select_option(str(saved["id"]))
        expect(page.get_by_label("策略名称")).to_have_value(name)
        page.get_by_label("初始资金", exact=True).fill(str(cash))
        fill_date(page, "起始日期", start)
        fill_date(page, "结束日期", end)
        page.get_by_label("基准", exact=True).fill(benchmark)
        if key == "rebalance":
            page.get_by_text("原始价(none)", exact=True).click()
            page.get_by_text("前复权(pre)", exact=True).click()
        page.screenshot(path=str(OUT / f"{key}-editor.png"))
        with page.expect_response(lambda r: r.url.endswith("/api/backtest/async")) as response:
            page.get_by_role("button", name="运行策略回测", exact=True).click()
        submission = response.value.json()
        assert response.value.ok, submission
        run_id = submission["run_id"]
        print("SUBMITTED", key, run_id, flush=True)
        expect(page.locator(".run-status")).to_contain_text("状态：SUCCESS", timeout=240000)
        page.locator(".returns-chart:visible canvas").wait_for()
        expect(page.locator(".console-output")).not_to_contain_text("等待策略运行")
        page.screenshot(path=str(OUT / f"{key}-result.png"))
        run = page.request.get(URL + f"api/backtest/runs/{run_id}").json()
        assert run["config"]["strategy_source"] == saved["source"]
        assert run["config"]["initial_cash"] == cash
        assert run["config"]["start_date"] == start and run["config"]["end_date"] == end
        assert run["config"]["benchmark"] == benchmark
        assert run["config"]["fq"] == ("pre" if key == "rebalance" else "none")
        page.get_by_role("button", name="打开完整回测报告 →").click()
        page.locator(".returns-chart:visible canvas").wait_for()
        native = page.request.get(URL + f"api/backtest/runs/{run_id}/report-data").json()
        directory = Path(run["config"]["run_dir"])
        assert native["metrics"] == json.loads((directory / "metrics.json").read_text(), parse_constant=str)["metrics"]
        with (directory / "daily_records.csv").open(encoding="utf-8-sig") as stream:
            assert native["daily"]["rows"] == list(csv.DictReader(stream))
        expect(page.locator(".report-content .report-metric").filter(has_text="策略收益").first).to_contain_text(str(native["metrics"]["策略收益"]))
        page.screenshot(path=str(OUT / f"{key}-report.png"))
        for label, table_key in [("交易详情", "trades"), ("每日持仓", "positions"), ("每日收益", "daily")]:
            section(page, label)
            expect(page.locator(".native-table")).to_be_visible()
            assert native[table_key]["rows"], table_key
            expect(page.locator(".native-table")).to_contain_text(f"共 {len(native[table_key]['rows'])} 条")
            page.screenshot(path=str(OUT / f"{key}-{table_key}.png"))
        section(page, "日志输出")
        expect(page.locator(".report-console")).not_to_have_text("加载中…")
        assert len(page.locator(".report-console").inner_text()) > 50
        section(page, "策略代码")
        expect(page.locator(".report-console")).to_contain_text("# joinquant layout browser edit")
        section(page, "报告文件")
        expect(page.get_by_role("link", name="standard_report.html", exact=True)).to_be_visible()
        section(page, "配置与审计")
        expect(page.locator(".audit-content")).to_contain_text(benchmark)
        page.get_by_role("button", name="← 返回继续编辑").click()
        expect(page.get_by_label("策略名称")).to_have_value(name)
        page.get_by_label("策略名称").fill("未保存的草稿")
        page.get_by_text("回测详情", exact=True).last.click()
        section(page, "收益概述")
        page.get_by_role("button", name="← 返回继续编辑").click()
        expect(page.get_by_label("策略名称")).to_have_value("未保存的草稿")
        page.get_by_text("回测列表", exact=True).click()
        page.get_by_label("搜索回测").fill(run_id)
        page.get_by_role("button", name="恢复源码与配置", exact=True).click()
        expect(page.get_by_label("策略名称")).to_have_value(name)
        expect(page.get_by_label("初始资金", exact=True)).to_have_value(str(cash))
        expect(page.get_by_label("起始日期", exact=True)).to_have_value(start)
        expect(page.get_by_label("结束日期", exact=True)).to_have_value(end)
        record = {"sample": key, "run_id": run_id, "strategy_id": saved["id"], "config": run["config"], "result_hash": run["result_hash"], "metrics": native["metrics"], "rows": {k: len(native[k]["rows"]) for k in ["daily", "trades", "positions"]}, "page_errors": errors, "browser_workflow": "PASS"}
        records.append(record)
        (OUT / "runs.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))
        print("BROWSER_PASS", key, record["rows"], flush=True)
        assert not errors, errors
        if key != "rebalance":
            page.close()

    # Every global menu is reachable and the editor draft survives navigation.
    for label in ["数据状态", "研报", "实验对比", "运行记录", "策略回测"]:
        page.locator(".global-header").get_by_text(label, exact=True).click()
        page.screenshot(path=str(OUT / f"navigation-{label}.png"))
    expect(page.get_by_label("策略名称")).to_have_value(name)
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_function("document.querySelector('.preview-pane .returns-chart canvas').getBoundingClientRect().width < 390")
    expect(page.get_by_role("button", name="运行策略回测", exact=True)).to_be_visible()
    page.screenshot(path=str(OUT / "mobile-editor.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.set_viewport_size({"width": 1600, "height": 1000})
    page.locator(".monaco-editor").click()
    page.keyboard.press("Control+End")
    page.keyboard.press("Enter")
    page.keyboard.type("raise RuntimeError('layout browser expected failure')")
    with page.expect_response(lambda r: r.url.endswith("/api/backtest/async")) as response:
        page.get_by_role("button", name="运行策略回测", exact=True).click()
    failure_id = response.value.json()["run_id"]
    expect(page.locator(".run-status")).to_contain_text("状态：FAILED", timeout=120000)
    expect(page.locator(".preview-result")).to_contain_text("layout browser expected failure")
    page.get_by_role("button", name="错误 · 1", exact=True).click()
    expect(page.locator(".console-output")).to_contain_text("layout browser expected failure")
    page.screenshot(path=str(OUT / "failure.png"))
    (OUT / "checks.json").write_text(json.dumps({"base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(), "url": URL, "failure_run": failure_id, "save_reopen": True, "report_return_draft": True, "history_restore": True, "menus": True, "mobile_no_horizontal_overflow": True}, ensure_ascii=False, indent=2))
    browser.close()
