"""Real browser checks for report navigation, immutable recovery, rerun and failure."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

out = Path('docs/acceptance/local-backtest')
original = json.loads((out / 'buyhold.json').read_text())['submission']
evidence = {'original_run_id': original['run_id'], 'steps': []}
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1600, 'height': 1100})
    page.goto('http://127.0.0.1:7231/')
    page.get_by_label('载入样例').select_option('dma')
    page.get_by_label('策略名称').fill('不应覆盖历史的编辑草稿')
    page.get_by_label('初始资金', exact=True).fill('123456')
    page.get_by_text('运行记录', exact=True).first.click()
    page.locator('tr').filter(has_text=original['run_id']).click()
    page.get_by_role('button', name='打开完整报告 →').first.click()
    page.get_by_role('heading', name='回测报告 · ' + original['run_id']).wait_for()
    page.get_by_text('策略回测', exact=True).click()
    expect(page.get_by_label('策略名称')).to_have_value('不应覆盖历史的编辑草稿')
    expect(page.get_by_label('初始资金', exact=True)).to_have_value('123456')
    evidence['steps'].append('从历史报告点击策略菜单，仍保留编辑草稿和123456资金')
    for label in ('数据状态', '研报', '实验对比', '策略回测', '运行记录'):
        page.get_by_role('menuitem', name=label).click()
        expect(page.locator('.ant-menu-item-selected')).to_contain_text(label)
        assert page.locator('iframe[title="BulletTrade 回测报告"]').count() == 0
    page.locator('tr').filter(has_text=original['run_id']).click()
    page.get_by_role('button', name='恢复源码与配置').click()
    expect(page.get_by_label('策略名称')).to_have_value(original['config']['strategy_name'])
    expect(page.get_by_label('初始资金', exact=True)).to_have_value('500000')
    with page.expect_response(lambda r: r.url.endswith('/api/backtest/async')) as response:
        page.get_by_role('button', name='运行策略回测', exact=True).click()
    recovered = response.value.json()
    for key in ('strategy_source', 'initial_cash', 'start_date', 'end_date', 'frequency', 'benchmark', 'fq', 'extras'):
        assert recovered['config'][key] == original['config'][key], key
    evidence['recovered_submission'] = recovered
    print('RECOVERED', recovered['run_id'], flush=True)
    page.get_by_role('button', name='打开完整回测报告 →').wait_for(timeout=180000)
    evidence['steps'].append('改变草稿后恢复历史，浏览器重新提交的源码及全部配置与原运行逐字段一致；重新运行成功')
    page.screenshot(path=str(out / 'history-recovered.png'), full_page=True)
    # Deliberately failing strategy, entered using real keyboard events.
    page.locator('.monaco-editor').click()
    page.keyboard.press('Control+End')
    page.keyboard.press('Enter')
    page.keyboard.type("raise RuntimeError('browser_expected_failure')")
    with page.expect_response(lambda r: r.url.endswith('/api/backtest/async')) as response:
        page.get_by_role('button', name='运行策略回测', exact=True).click()
    failed = response.value.json()
    evidence['failed_submission'] = failed
    page.get_by_text('回测失败', exact=True).wait_for(timeout=60000)
    expect(page.locator('body')).to_contain_text('browser_expected_failure')
    page.screenshot(path=str(out / 'expected-task-failure.png'), full_page=True)
    evidence['steps'].append('键盘输入故意失败策略，提交后页面显示FAILED及具体异常，未显示成功报告入口')
    assert not page.get_by_role('button', name='打开完整回测报告 →').count()
    page.get_by_role('menuitem', name='运行记录').click()
    page.locator('tr').filter(has_text=failed['run_id']).click()
    expect(page.locator('body')).to_contain_text('browser_expected_failure')
    evidence['browser_workflow'] = 'PASS'
    (out / 'recovery-failure.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    browser.close()
