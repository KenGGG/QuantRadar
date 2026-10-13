"""Launch original ETF strategy through the real strategy-list UI."""
import hashlib
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/acceptance/quantradar2-qmt-parity'
SID='9f4c83d116b74ece9335ff5881acd704'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1900,'height':1100})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        api=page.request;url='http://127.0.0.1:7242/api/v2'
        before=api.get(url+'/strategies/'+SID).json()
        page.goto('http://127.0.0.1:7242/',wait_until='networkidle')
        page.get_by_text(before['name'],exact=True).first.click()
        for label,value in [('开始日期','2019-01-01'),('结束日期','2025-12-05')]:
            box=page.get_by_role('textbox',name=label,exact=True)
            box.click();box.fill(value);box.press('Enter');expect(box).to_have_value(value)
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/v2/runs'),timeout=30000) as response:
            page.get_by_role('button',name='运行回测',exact=True).click()
        result=response.value
        assert result.status==202,result.text()
        run=result.json()
        expect(page.locator('[aria-live="polite"]').filter(has_text=run['id'][:8])).to_be_visible(timeout=10000)
        after=api.get(url+'/strategies/'+SID).json()
        assert before['source']==after['source']
        assert before['revision_id']==after['revision_id']==run['revision_id']
        page.wait_for_timeout(350);page.screenshot(path=str(OUT/'launch.png'),full_page=True)
        assert not errors,errors
        (OUT/'launch.json').write_text(json.dumps({'run_id':run['id'],'source_sha256':hashlib.sha256(before['source'].encode()).hexdigest(),
            'revision_id':before['revision_id'],'source_and_revision_unchanged':True,
            'visible_submission_feedback':True,'page_errors':errors,'request':run['request']},ensure_ascii=False,indent=2),encoding='utf-8')
        print(run['id'])
        browser.close()

if __name__=='__main__':main()
