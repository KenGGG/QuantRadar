"""Read-only browser acceptance for range selection and return tooltips."""
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'var/quantradar2/chart-interaction'
OUT.mkdir(parents=True, exist_ok=True)
run = json.loads((ROOT / 'docs/acceptance/quantradar2-qmt-parity/run.json').read_text(encoding='utf-8'))
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width':1600, 'height':1100})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.route('**/api/v2/runs', lambda r: r.fulfill(json=[run]))
    page.route('**/api/v2/runs?*', lambda r: r.fulfill(json=[run]))
    page.goto('http://127.0.0.1:7242/', wait_until='networkidle')
    page.get_by_role('menuitem', name='记录与报告').click()
    page.locator('tbody').get_by_role('button', name='回测详情', exact=True).click()
    nav = page.locator('.jq-time-navigator')
    expect(nav).to_be_visible(timeout=15000)
    chart = page.locator('.jq-main-curve')
    def hover_check():
        chart.scroll_into_view_if_needed()
        box = chart.bounding_box()
        page.mouse.move(box['x']+box['width']*.55, box['y']+box['height']*.2)
        tip = page.locator('.jq-curve-tooltip')
        expect(tip).to_be_visible()
        assert '策略收益' in tip.text_content() and '基准收益' in tip.text_content()
        records = page.request.get(f"http://127.0.0.1:7242/api/v2/runs/{run['id']}/artifacts/daily_records.csv").text()
        import csv, io
        data = {r['date'][:10]: r for r in csv.DictReader(io.StringIO(records.lstrip(chr(0xfeff))))}
        labels = tip.locator('text').all_text_contents()
        row = data[labels[0]]
        for label, key in zip(labels[1:], ['returns_pct', 'benchmark_returns_pct']):
            actual = float(label.split('：')[1].replace('%','').replace(',',''))
            assert abs(actual-float(row[key])) <= .0051
    hover_check()
    nav.scroll_into_view_if_needed()
    before = nav.locator('strong').inner_text()
    handle = nav.get_by_role('slider').first
    box = handle.bounding_box()
    track = page.locator('.jq-navigator-track').bounding_box()
    page.mouse.move(box['x']+box['width']/2, box['y']+box['height']/2)
    page.mouse.down()
    page.mouse.move(track['x']+track['width']*.3, box['y']+box['height']/2, steps=15)
    page.mouse.up()
    assert before != nav.locator('strong').inner_text()
    hover_check()
    handle.focus()
    before = handle.get_attribute('aria-valuenow')
    page.keyboard.press('ArrowRight')
    assert handle.get_attribute('aria-valuenow') != before
    nav.scroll_into_view_if_needed()
    selected_track = nav.locator('.ant-slider-track').bounding_box()
    before = nav.locator('strong').inner_text()
    page.mouse.move(selected_track['x']+selected_track['width']/2, selected_track['y']+25)
    page.mouse.down()
    page.mouse.move(selected_track['x']+selected_track['width']/2-40, selected_track['y']+25, steps=10)
    page.mouse.up()
    assert nav.locator('strong').inner_text() != before
    page.get_by_role('button', name=re.compile(r'^全\s*部$')).click()
    assert nav.locator('strong').inner_text().startswith('2019-01-02')
    page.screenshot(path=str(OUT/'desktop.png'), full_page=True)
    page.set_viewport_size({'width':390, 'height':844})
    expect(nav).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(OUT/'mobile.png'), full_page=True)
    assert not errors, errors
    print('Chart tooltip values, range dragging, keyboard selection, reset and mobile layout passed.')
    browser.close()




