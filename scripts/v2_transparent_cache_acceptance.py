"""Check transparent preparation with no source declaration or UI data plan, mocking writes to preserve user data."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright,expect
OUT=Path(__file__).resolve().parents[1]/'docs/acceptance/quantradar2-transparent-cache'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        context=browser.new_context(viewport={'width':1700,'height':1000});page=context.new_page();errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:7242/',wait_until='networkidle')
        page.get_by_role('menuitem',name='策略工作台').click()
        page.get_by_role('button',name='⚙ 设置').click()
        expect(page.get_by_text('强制先缓存数据，再本地回测',exact=True)).to_be_visible()
        expect(page.get_by_text('系统自动识别策略的数据需求，完成缓存和校验后再回测。无需修改策略代码或填写数据清单。',exact=True)).to_be_visible()
        assert page.get_by_placeholder('数据需求 JSON',exact=False).count()==0
        page.wait_for_timeout(350)  # let the modal opening transition settle
        page.screenshot(path=str(OUT/'settings.png'),full_page=True)
        page.locator('.ant-modal-footer button').click()
        strategy=context.request.get('http://127.0.0.1:7242/api/v2/strategies').json()[0]
        saved_sources=[]
        def save_capture(route):
            if route.request.method=='POST':
                saved_sources.append(route.request.post_data_json['source'])
                route.fulfill(json=strategy)
            else:route.continue_()
        page.route('**/api/v2/strategies',save_capture)
        submitted=[]
        def capture(route):
            if route.request.method=='POST':
                submitted.append(route.request.post_data_json)
                route.fulfill(status=400,json={'detail':'PREPARED_MODE_INTERCEPTED'})
            else:route.continue_()
        page.route('**/api/v2/runs',capture)
        page.get_by_role('button',name='运行回测',exact=True).click()
        expect(page.get_by_text('PREPARED_MODE_INTERCEPTED',exact=True)).to_be_visible()
        assert submitted[0]['data_mode']=='prepared' and submitted[0]['data_requirements'] is None
        assert saved_sources and 'DATA_REQUIREMENTS' not in saved_sources[0]
        assert not errors,errors
        (OUT/'browser.json').write_text(json.dumps({'passed':True,'page_errors':errors,'requested_mode':submitted[0]['data_mode'],'requests_mocked':True},ensure_ascii=False,indent=2),encoding='utf-8')
        browser.close()

if __name__=='__main__':main()
