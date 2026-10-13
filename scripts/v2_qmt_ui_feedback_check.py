"""Verify failed submissions are visible; intercept POST without creating a job."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/acceptance/quantradar2-qmt-parity'

with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1900,'height':1100})
    strategy=page.request.get('http://127.0.0.1:7242/api/v2/strategies/9f4c83d116b74ece9335ff5881acd704').json()
    page.goto('http://127.0.0.1:7242/',wait_until='networkidle')
    page.get_by_text(strategy['name'],exact=True).first.click()
    submitted=[]
    def fail(route):
        if route.request.method=='POST':
            submitted.append(route.request.post_data_json)
            route.fulfill(status=503,json={'detail':'DATA_SERVICE_UNAVAILABLE_CHECK'})
        else:route.continue_()
    page.route('**/api/v2/runs',fail)
    page.get_by_role('button',name='运行回测',exact=True).click()
    expect(page.locator('.preview-pane').get_by_text('DATA_SERVICE_UNAVAILABLE_CHECK',exact=True)).to_be_visible()
    assert len(submitted)==1
    page.wait_for_timeout(350);page.screenshot(path=str(OUT/'submission-error.png'),full_page=True)
    (OUT/'submission-error.json').write_text(json.dumps({'passed':True,'submitted_once':True,'error_visible_inside_workbench':True,
                                                      'run_post_intercepted':True},indent=2),encoding='utf-8')
    browser.close()

    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1900,'height':1100})
    pending=page.request.get('http://127.0.0.1:7242/api/v2/runs/5895a74a4635451f9b3e958d4e09143b').json()
    pending['status']='RUNNING'
    def queue(route):
        if route.request.method=='POST':route.fulfill(status=202,json=pending)
        else:route.continue_()
    page.route('**/api/v2/runs',queue)
    page.route('**/api/v2/runs/'+pending['id'],lambda route:route.fulfill(json=pending))
    page.route('**/api/v2/runs/'+pending['id']+'/artifacts',lambda route:route.fulfill(json=[]))
    page.goto('http://127.0.0.1:7242/',wait_until='networkidle')
    page.get_by_text(strategy['name'],exact=True).first.click()
    page.get_by_role('button',name='运行回测',exact=True).click()
    expect(page.get_by_text('数据准备或回测正在进行，完成后将显示收益曲线；可在下方查看日志。',exact=True)).to_be_visible()
    expect(page.locator('[aria-live="polite"]').filter(has_text=pending['id'][:8])).to_be_visible()
    page.wait_for_timeout(350);page.screenshot(path=str(OUT/'running-feedback.png'),full_page=True)
    (OUT/'running-feedback.json').write_text(json.dumps({'passed':True,'pending_placeholder_visible':True,
                                                       'run_post_intercepted':True},indent=2),encoding='utf-8')
    browser.close()
