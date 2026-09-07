"""Actual deployed-browser acceptance; no mocked API, data, engine or reports.
Run: .venv/bin/python scripts/accept_backtest_browser.py [buyhold|dma|rebalance]
"""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT = Path('docs/acceptance/local-backtest')
OUT.mkdir(parents=True, exist_ok=True)
key = sys.argv[1] if len(sys.argv) > 1 else 'buyhold'
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1600, 'height': 1100})
    evidence = {'sample': key, 'url': 'http://127.0.0.1:7231/', 'steps': []}
    page.on('pageerror', lambda e: print('PAGE_ERROR', str(e), flush=True))
    page.goto(evidence['url'])
    page.get_by_label('载入样例').select_option(key)
    name = page.get_by_label('策略名称').input_value() + ' 浏览器验收'
    page.get_by_label('策略名称').fill(name)
    page.locator('.monaco-editor textarea').wait_for(timeout=60000)
    editor = page.locator('.monaco-editor textarea')
    page.locator('.monaco-editor').click()
    page.keyboard.press('Control+End')
    page.keyboard.press('Enter')
    page.keyboard.type('# browser saved edit')
    with page.expect_response(lambda r: r.url.endswith('/api/strategies') and r.request.method == 'POST') as response:
        page.get_by_role('button', name='保存策略版本').click()
    saved = response.value.json()
    assert response.value.ok, saved
    assert '# browser saved edit' in saved['source']
    evidence['strategy'] = saved
    page.get_by_label('载入样例').select_option('dma' if key != 'dma' else 'buyhold')
    page.get_by_label('打开策略版本').select_option(str(saved['id']))
    expect(page.get_by_label('策略名称')).to_have_value(name)
    evidence['steps'].append('保存策略版本 → 切换样例 → 重新打开已保存版本')
    # Reload proves server-backed save survives a fresh page.
    page.reload()
    page.get_by_label('打开策略版本').select_option(str(saved['id']))
    expect(page.get_by_label('策略名称')).to_have_value(name)
    page.locator('.monaco-editor textarea').wait_for(timeout=60000)
    page.get_by_label('初始资金', exact=True).fill({'buyhold': '500000', 'dma': '600000', 'rebalance': '900000'}[key])
    if key == 'dma':
        page.get_by_label('基准', exact=True).fill('600519.XSHG')
        page.get_by_label('起始日期', exact=True).fill('2023-02-01')
        page.get_by_label('起始日期', exact=True).press('Enter')
        page.get_by_label('结束日期', exact=True).fill('2023-02-28')
        page.get_by_label('结束日期', exact=True).press('Enter')
    if key == 'rebalance':
        page.get_by_label('结束日期', exact=True).fill('2023-01-31')
        page.get_by_label('结束日期', exact=True).press('Enter')
        page.get_by_text('原始价(none)', exact=True).click()
        page.get_by_text('前复权(pre)', exact=True).click()
    page.screenshot(path=str(OUT / f'{key}-editor.png'), full_page=True)
    with page.expect_response(lambda r: r.url.endswith('/api/backtest/async')) as response:
        page.get_by_role('button', name='运行策略回测', exact=True).click()
    submission = response.value.json()
    assert response.value.ok, submission
    assert submission['config']['strategy_source'] == saved['source']
    evidence['submission'] = submission
    (OUT / f'{key}.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    print('SUBMITTED', submission['run_id'], flush=True)
    try:
        page.wait_for_function("document.body.innerText.includes('状态：SUCCESS') || document.body.innerText.includes('状态：FAILED')", timeout=240000)
        assert '状态：FAILED' not in page.locator('body').inner_text()
        page.get_by_role('button', name='打开完整回测报告 →').wait_for()
    except Exception:
        print(page.locator('body').inner_text(), flush=True)
        page.screenshot(path=str(OUT / f'{key}-failure.png'), full_page=True)
        raise
    page.get_by_role('button', name='打开完整回测报告 →').click()
    frame = page.frame_locator('iframe[title="BulletTrade 回测报告"]')
    frame.locator('body').wait_for()
    text = frame.locator('body').inner_text()
    print('REPORT', text[:2500], flush=True)
    assert f"{submission['config']['initial_cash']:,.2f}" in text
    evidence['standard_report_text'] = text
    page.screenshot(path=str(OUT / f'{key}-report.png'), full_page=True)
    page.get_by_role('button', name='详细报告', exact=True).click()
    frame.locator('summary').first.wait_for(timeout=20000)
    expect(frame.locator('body')).to_contain_text('策略收益', timeout=20000)
    evidence['full_report_text'] = frame.locator('body').inner_text()
    print('DETAILS', frame.locator('summary').all_text_contents(), flush=True)
    for term in ('trades.csv', 'daily_positions.csv'):
        summary = frame.locator('summary').filter(has_text=term).first
        assert summary.count(), f'详细报告缺少 {term}'
        summary.click()
        expect(summary.locator('..').locator('table')).to_be_visible()
    page.screenshot(path=str(OUT / f'{key}-details.png'), full_page=True)
    page.get_by_role('button', name='查看日志', exact=True).click()
    expect(page.get_by_text('回测日志', exact=True)).to_be_visible()
    evidence['log_text'] = page.locator('pre').inner_text()
    page.screenshot(path=str(OUT / f'{key}-logs.png'), full_page=True)
    page.get_by_role('button', name='关闭日志', exact=True).click()
    page.get_by_role('button', name='← 返回继续编辑').click()
    expect(page.get_by_label('策略名称')).to_have_value(name)
    page.get_by_text('运行记录', exact=True).first.click()
    page.locator('tr').filter(has_text=submission['run_id']).click()
    page.get_by_role('button', name='恢复源码与配置').click()
    expect(page.get_by_label('策略名称')).to_have_value(name)
    expect(page.get_by_label('初始资金', exact=True)).to_have_value(str(submission['config']['initial_cash']).removesuffix('.0'))
    evidence['steps'].extend(['刷新页面重新打开已保存版本', '页面配置资金 → 提交真实回测 → 打开聚宽风格报告', '查看详细报告 → 返回继续编辑', '运行记录 → 恢复历史源码与配置'])
    evidence['browser_workflow'] = 'PASS'
    (OUT / f'{key}.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    browser.close()
