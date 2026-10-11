"""Read-only browser acceptance of existing immutable backtest results."""
from pathlib import Path
import json,re
from playwright.sync_api import sync_playwright, expect

OUT = Path(__file__).resolve().parents[1] / 'docs/acceptance/quantradar2-metrics-editor'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(viewport={'width':1700,'height':1050})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:7242/', wait_until='networkidle')
        page.get_by_role('menuitem', name='记录与报告').click()
        runs = context.request.get('http://127.0.0.1:7242/api/v2/runs').json()
        index = next(i for i,r in enumerate(runs) if r['id']=='183c460311b14371a09cbec982ba29aa')
        if index >= 10:
            page.locator('.ant-pagination-item').filter(has_text=str(index//10+1)).click()
        page.locator('.ant-table-tbody tr').nth(index%10).get_by_role('button', name='回测详情', exact=True).click()
        page.locator('.jq-metrics strong').first.wait_for()
        page.wait_for_function("document.querySelector('.jq-chart svg[role=img] path') !== null")
        page.locator(".jq-panel h3 small").wait_for(state="detached")
        assert page.locator('.jq-chart svg[role=img] path').count() == 3
        page.screenshot(path=str(OUT/'overview.png'), full_page=True)
        page.get_by_role('checkbox', name='超额收益', exact=True).click()
        expect(page.locator('.jq-chart svg[role=img] path')).to_have_count(4)
        page.get_by_role('checkbox', name='对数轴').click()
        page.get_by_role('button', name='1个月', exact=True).click()
        page.get_by_role('button', name=re.compile(r'全\s*部')).click()
        for title in ['交易详情','每日持仓&收益']:
            page.locator('.jq-sidebar').get_by_role('button', name=title).click()
            assert page.locator('.jq-panel .ant-table-tbody tr').count() > 0
            page.get_by_role('button', name='按日分组').click()
            page.locator('.jq-panel .ant-table-row-expand-icon').first.click()
            page.screenshot(path=str(OUT/('trades.png' if title=='交易详情' else 'positions.png')), full_page=True)
        page.locator('.jq-sidebar').get_by_role('button', name='日志输出').click()
        page.get_by_role('checkbox', name='仅错误 / 警告日志').click()
        page.locator('.jq-sidebar').get_by_role('button', name='性能分析').click()
        assert '引擎回测' in page.locator('.jq-console').inner_text()
        page.locator('.jq-sidebar').get_by_role('button', name='策略代码').click()
        page.locator('.jq-panel .monaco-editor').wait_for()
        page.locator('.jq-sidebar').get_by_role('button', name='策略收益').click()
        assert page.locator('.jq-panel .ant-table-tbody tr').count() > 0
        page.locator('.jq-sidebar').get_by_role('button', name='阿尔法').click()
        assert page.locator('.jq-metric-summary strong').inner_text() != '—'
        assert page.locator('.jq-panel .ant-table-tbody tr').count() > 12
        page.screenshot(path=str(OUT/'rolling-alpha.png'), full_page=True)
        page.locator('.jq-sidebar').get_by_role('button', name='收益概述').click()
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUT/'mobile.png'), full_page=True)
        assert page.locator('.jq-sidebar').evaluate('(e)=>e.scrollWidth > e.clientWidth')
        page.set_viewport_size({'width':1700,'height':1050})
        page.get_by_role('button', name='恢复代码与参数', exact=True).click()
        page.locator('.jq-workbench .monaco-editor').wait_for()
        assert page.locator('.jq-preview-metrics strong').count() == 6
        page.screenshot(path=str(OUT/'editor.png'), full_page=True)
        page.get_by_role('button', name='⚙ 设置').click()
        page.get_by_role('checkbox', name='代码自动换行').click()
        page.get_by_role('button', name=re.compile(r'完\s*成')).click()
        page.get_by_role('button', name='错误', exact=True).click()
        page.get_by_role('button', name=re.compile(r'收\s*起')).click()
        assert page.locator('.jq-editor-console').count() == 0
        page.get_by_role('button', name=re.compile(r'展\s*开')).click()
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUT/'editor-mobile.png'), full_page=True)
        assert not errors, errors
        (OUT/'browser.json').write_text(json.dumps({'passed':True,'page_errors':errors,'checks':['application daily metrics','strategy/benchmark/excess charts','log axis and time range','trades and positions with day grouping','error log filter','phase timing','immutable code','monthly rolling returns and alpha','mobile navigation','editor split layout and summary','advanced settings and word wrap','editor error log and collapse','mobile editor']},ensure_ascii=False,indent=2), encoding='utf-8')
        browser.close()

if __name__ == '__main__':
    main()
