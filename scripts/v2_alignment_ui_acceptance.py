"""Read real immutable artifacts and verify displayed/exported application metrics."""
import json
from pathlib import Path
import urllib.request
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/acceptance/quantradar2-jq-alignment'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with urllib.request.urlopen('http://127.0.0.1:7242/api/v2/runs/ec85355092904cf88e3eea429bd0929c') as r:run=json.load(r)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1900,'height':1100},accept_downloads=True)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/api/v2/runs?*',lambda route:route.fulfill(json=[run]))
        page.route('**/api/v2/runs',lambda route:route.fulfill(json=[run]))
        page.goto('http://127.0.0.1:7242/',wait_until='networkidle')
        page.get_by_role('menuitem',name='记录与报告').click()
        page.locator('tbody').get_by_role('button',name='回测详情',exact=True).click()
        expect(page.get_by_text('779.1543%',exact=True)).to_be_visible()
        page.get_by_role('button',name='导出 ▾',exact=True).click()
        with page.expect_download() as info:
            page.get_by_role('menuitem',name='应用指标 JSON',exact=True).click()
        payload=json.loads(Path(info.value.path()).read_text(encoding='utf-8'))
        assert payload['run_id']==run['id']
        expected=json.loads((ROOT/'var/quantradar2/jq-alignment-validation/application-metrics.json').read_text(encoding='utf-8'))['actual']
        for key,value in expected.items():
            actual=payload['statistics'][key]
            if isinstance(value,(float,int)):assert abs(actual-value)<1e-9,(key,actual,value)
            else:assert actual==value
        page.wait_for_timeout(350)
        page.screenshot(path=str(OUT/'details.png'),full_page=True)
        assert not errors,errors
        (OUT/'browser.json').write_text(json.dumps({'passed':True,'run_id':run['id'],'download_matches_calculation':True,'page_errors':errors},indent=2),encoding='utf-8')
        browser.close()

if __name__=='__main__':main()
