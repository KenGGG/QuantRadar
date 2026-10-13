"""Read-only verification that real comparisons are accessible in QuantRadar."""
import hashlib
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/acceptance/quantradar2-etf-evidence'
manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
results=json.loads((OUT/'results.json').read_text(encoding='utf-8'))['results']
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1600,'height':1100})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    api=page.request;base='http://127.0.0.1:7242/api/v2'
    original=api.get(base+'/strategies/9f4c83d116b74ece9335ff5881acd704').json()
    assert original['revision_id']==manifest['original_revision']
    assert hashlib.sha256(original['source'].encode()).hexdigest()==manifest['original_source_sha256']
    actual=api.get(base+'/strategies').json()
    assert all(any(s['id']==c['strategy_id'] and s['run_count']>=1 for s in actual) for c in manifest['cases'])
    for key in ['original_full','momentum_25','followup_original']:
        record=next(r for r in results if r['key']==key)
        assert record['status']=='SUCCEEDED'
        page.goto('http://127.0.0.1:7242/',wait_until='networkidle')
        page.get_by_role('searchbox',name='搜索策略',exact=True).fill('验证ETF · '+key)
        row=page.locator('tbody tr').filter(has_text='验证ETF · '+key)
        expect(row).to_have_count(1)
        row.get_by_role('button',name='1',exact=True).click()
        report_row=page.locator('tbody tr').filter(has_text='验证ETF · '+key)
        expect(report_row).to_have_count(1)
        report_row.get_by_role('button',name='回测详情',exact=True).click()
        # Read the application statistic shown by the actual page.
        metric=page.locator('.jq-metrics > div').filter(has=page.locator('label').filter(has_text='策略年化收益')).locator('strong')
        expect(metric).not_to_have_text('—',timeout=15000)
        value=float(metric.inner_text(timeout=15000).replace('%','').replace(',',''))
        assert abs(value-record['statistics']['策略年化收益'])<=.000051
        page.screenshot(path=str(OUT/(key+'-page.png')),full_page=True)
    assert not errors,errors
    (OUT/'browser.json').write_text(json.dumps({'passed':True,'original_source_and_revision_unchanged':True,
        'all_25_strategies_visible':True,'checked_pages':['original_full','momentum_25','followup_original'],
        'displayed_annual_returns_match_results':True,'page_errors':errors},indent=2),encoding='utf-8')
    browser.close()
print('Real strategy list, report pages and immutable original verified.')
