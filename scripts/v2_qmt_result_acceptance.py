"""Check real QMT result display and downloadable application statistics."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/acceptance/quantradar2-qmt-parity'
run=json.loads((OUT/'run.json').read_text(encoding='utf-8'))
expected=json.loads((OUT/'application-metrics.json').read_text(encoding='utf-8'))['actual']
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1900,'height':1100},accept_downloads=True)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    # Limit only the listing for deterministic selection; all run/artifact reads are real.
    page.route('**/api/v2/runs',lambda route:route.fulfill(json=[run]))
    page.route('**/api/v2/runs?*',lambda route:route.fulfill(json=[run]))
    page.goto('http://127.0.0.1:7242/',wait_until='networkidle')
    page.get_by_role('menuitem',name='记录与报告').click()
    page.locator('tbody').get_by_role('button',name='回测详情',exact=True).click()
    expect(page.get_by_text('740.3669%',exact=True)).to_be_visible(timeout=10000)
    expect(page.get_by_text('1.6912',exact=True)).to_be_visible()
    page.get_by_role('button',name='导出 ▾',exact=True).click()
    with page.expect_download() as info:
        page.get_by_role('menuitem',name='应用指标 JSON',exact=True).click()
    payload=json.loads(Path(info.value.path()).read_text(encoding='utf-8'))
    for key,value in expected.items():
        own=payload['statistics'][key]
        if isinstance(value,(float,int)):assert abs(own-value)<1e-9,(key,own,value)
        else:assert own==value
    assert payload['run_id']==run['id']
    page.wait_for_timeout(350);page.screenshot(path=str(OUT/'details.png'),full_page=True)
    assert not errors,errors
    (OUT/'browser.json').write_text(json.dumps({'passed':True,'run_id':run['id'],
        'displayed_return':'740.3669%','displayed_sortino':'1.6912',
        'export_matches_all_application_metrics':True,'page_errors':errors},indent=2),encoding='utf-8')
    browser.close()
