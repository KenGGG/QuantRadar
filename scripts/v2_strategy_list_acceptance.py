"""Create one identifiable blank draft, edit/save, and archive it after UI acceptance."""
from pathlib import Path
import json,time,re
from playwright.sync_api import sync_playwright,expect
OUT=Path(__file__).resolve().parents[1]/'docs/acceptance/quantradar2-strategy-list'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        context=browser.new_context(viewport={'width':1700,'height':1000})
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:7242/',wait_until='networkidle')
        page.locator('.strategy-list h2').wait_for()
        page.screenshot(path=str(OUT/'list.png'),full_page=True)
        page.get_by_role('button',name='新建空白策略').click()
        name='UI blank draft acceptance '+str(int(time.time()))
        page.get_by_role('textbox',name='新策略名称').fill(name)
        with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/v2/strategies')) as response:
            page.get_by_role('button',name='创建并编辑').click()
        strategy=response.value.json();assert strategy['source']==''
        page.locator('.jq-workbench .monaco-editor').wait_for()
        page.screenshot(path=str(OUT/'blank-editor.png'),full_page=True)
        page.get_by_role('button',name='运行回测',exact=True).click()
        expect(page.get_by_text('请先编写策略代码，再运行回测',exact=True)).to_be_visible()
        # Type through the actual Monaco surface, without creating a backtest.
        page.locator('.monaco-editor .view-lines').click(position={'x':120,'y':10})
        page.keyboard.type('def initialize(context):\n    pass',delay=15)
        page.keyboard.press('Escape')
        with page.expect_response(lambda r:r.request.method=='PUT' and '/api/v2/strategies/' in r.url) as response:
            page.locator('.jq-editor-toolbar').get_by_role('button',name=re.compile(r'保\s*存')).first.click()
        saved=response.value.json();assert 'def initialize(context)' in saved['source']
        page.get_by_role('menuitem',name='策略列表',exact=True).click()
        search=page.get_by_placeholder('策略名称',exact=True);search.fill(name)
        row=page.locator('.strategy-list .ant-table-tbody tr').filter(has_text=name)
        expect(row).to_have_count(1)
        page.screenshot(path=str(OUT/'search.png'),full_page=True)
        row.get_by_role('button',name='0',exact=True).click()
        expect(page.get_by_role('heading',name=re.compile(name))).to_be_visible()
        expect(page.locator('.ant-table-tbody .ant-table-row')).to_have_count(0)
        page.get_by_role('menuitem',name='策略列表',exact=True).click()
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
        # Archive the acceptance draft; preserve its revision history.
        assert context.request.delete('http://127.0.0.1:7242/api/v2/strategies/'+strategy['id']).ok
        assert context.request.get('http://127.0.0.1:7242/api/v2/revisions/'+strategy['revision_id']).json()['source']==''
        assert not errors,errors
        (OUT/'browser.json').write_text(json.dumps({'passed':True,'strategy_id':strategy['id'],'test_draft_archived':True,'page_errors':errors,'checks':['default strategy list','named genuinely blank strategy','empty-code backtest guard','Monaco edit and save new revision','search','strategy-specific history','mobile layout','immutable blank revision retained']},ensure_ascii=False,indent=2),encoding='utf-8')
        browser.close()

if __name__=='__main__':main()
