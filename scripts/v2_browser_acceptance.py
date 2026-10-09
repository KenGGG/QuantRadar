"""Headless Edge acceptance using the visible Monaco editing surface."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import json,time,re
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"docs/acceptance/quantradar2-g2"
def edit(page,lines):
    page.locator(".monaco-editor .view-lines").click(position={"x":150,"y":8})
    page.keyboard.press("Control+a")
    for index,line in enumerate(lines):
        page.keyboard.type(line,delay=20);page.keyboard.press("Escape")
        if index<len(lines)-1:page.keyboard.press("Enter")
def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(channel="msedge",headless=True)
        context=browser.new_context(viewport={"width":1440,"height":1000});page=context.new_page()
        errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto("http://127.0.0.1:7242/",wait_until="networkidle")
        page.get_by_role("menuitem",name="记录与报告").click()
        cases=json.loads((OUT/"strategy-suite.json").read_text(encoding="utf-8"))
        source=cases[-1]["recorded"]
        runs=context.request.get("http://127.0.0.1:7242/api/v2/runs").json()
        index=next(i for i,r in enumerate(runs) if r["id"]==source)
        if index>=10:page.locator(".ant-pagination-item").filter(has_text=str(index//10+1)).click()
        page.locator(".ant-table-tbody tr").nth(index%10).get_by_role("button",name="日志与报告").click()
        page.locator(".detail").get_by_text(source[:8],exact=False).wait_for()
        with page.expect_response(lambda r:r.request.method=="POST" and r.url.endswith("/replay")) as response:
            page.get_by_role("button",name="离线回放冻结数据").click()
        run=response.value.json();print("browser offline replay",run["id"],flush=True)
        page.get_by_role("link",name="打开原生报告").wait_for(timeout=55000)
        assert page.locator(".detail").get_by_text("SUCCEEDED",exact=True).count()==1
        page.screenshot(path=str(OUT/"offline-replay.png"),full_page=True)
        report=context.new_page();report.goto("http://127.0.0.1:7242/api/v2/runs/"+run["id"]+"/report",wait_until="load")
        assert len(report.inner_text("body"))>100
        assert "500,000.00" in report.inner_text("body")
        report.screenshot(path=str(OUT/"native-report.png"),full_page=True);report.close()
        page.get_by_role("menuitem",name="策略工作台").click()
        label="G2 browser acceptance "+str(int(time.time()))
        page.locator(".toolbar input.ant-input").first.fill(label)
        edit(page,["def initialize(context):","broken ="])
        with page.expect_response(lambda r:r.url.endswith("/api/v2/runs") and r.request.method=="POST") as response:
            page.get_by_role("button",name="保存并回测",exact=True).click()
        failed=response.value.json()
        page.locator(".detail").get_by_text("FAILED",exact=True).wait_for(timeout=30000)
        page.screenshot(path=str(OUT/"failure.png"),full_page=True)
        print("browser syntax failure surfaced",flush=True)
        edit(page,["def initialize(context):","import time","print('BROWSER_SLEEP_ENTERED', flush=True)","time.sleep(60)"])
        with page.expect_response(lambda r:r.url.endswith("/api/v2/runs") and r.request.method=="POST") as response:
            page.get_by_role("button",name="保存并回测",exact=True).click()
        cancelled=response.value.json()
        page.locator(".detail").get_by_text("RUNNING",exact=True).wait_for(timeout=15000)
        page.get_by_role("button",name="停止回测",exact=True).click()
        page.locator(".detail").get_by_text("CANCELLED",exact=True).wait_for(timeout=15000)
        page.screenshot(path=str(OUT/"cancelled.png"),full_page=True)
        page.get_by_role("button",name="归档策略",exact=True).click()
        page.locator(".ant-modal-confirm-btns button").last.click()
        page.locator(".ant-modal-confirm").wait_for(state="detached")
        page.get_by_role("button",name="已归档策略",exact=True).click()
        row=page.locator(".ant-modal .ant-table-tbody tr").filter(has_text=label)
        row.get_by_role("button",name=re.compile(r"恢\s*复")).click();row.wait_for(state="detached")
        (OUT/"browser-final.json").write_text(json.dumps({"offline_replay":run["id"],"syntax_failure":failed["id"],"cancelled":cancelled["id"],"checks":["offline replay button","native report rendered","editor code changes saved","syntax failure visible","running task stopped","archive and restore preserve revision history"],"page_errors":errors,"passed":not errors},ensure_ascii=False,indent=2),encoding="utf-8")
        assert not errors;print("browser final checks passed",flush=True)
        browser.close()
if __name__=="__main__":main()
