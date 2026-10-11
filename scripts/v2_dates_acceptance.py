"""Read-only date navigation acceptance; intercept run submissions without saving or queueing."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright,expect
OUT=Path(__file__).resolve().parents[1]/'docs/acceptance/quantradar2-dates'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        context=browser.new_context(viewport={'width':1700,'height':1000});page=context.new_page();errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:7242/',wait_until='networkidle')
        page.get_by_role('menuitem',name='策略工作台').click()
        start=page.get_by_role('textbox',name='开始日期',exact=True)
        start.click();expect(page.get_by_role('spinbutton',name='开始日期年份')).to_be_visible()
        start.fill('2019-01-01');start.press('Enter');expect(start).to_have_value('2019-01-01')
        page.get_by_role('textbox',name='结束日期',exact=True).click()
        year=page.get_by_role('spinbutton',name='结束日期年份');year.fill('2019');year.press('Tab')
        page.get_by_role('combobox',name='结束日期月份').locator('..').locator('..').click()
        page.locator('.ant-select-item-option').filter(has_text='1月').first.click()
        page.locator('.ant-picker-cell:visible[title="2019-01-01"]').click()
        end=page.get_by_role('textbox',name='结束日期',exact=True);expect(end).to_have_value('2019-01-01')
        expect(page.get_by_role('spinbutton',name='结束日期年份')).not_to_be_visible()
        # Ordinary date grid and year/month header navigation remain functional.
        start.click();page.get_by_role('button',name='选择年份',exact=True).click()
        page.locator('.ant-picker-cell:visible').filter(has_text='2020').click()
        page.locator('.ant-picker-cell:visible[title="2020-02"]').click()
        page.locator('.ant-picker-cell:visible[title="2020-02-29"]').click()
        expect(start).to_have_value('2020-02-29')
        expect(page.get_by_role('spinbutton',name='开始日期年份')).not_to_be_visible()
        start.click();expect(page.get_by_role('spinbutton',name='开始日期年份')).to_be_visible()
        start.fill('2019-01-01');start.press('Enter')
        expect(page.get_by_role('spinbutton',name='开始日期年份')).not_to_be_visible()
        end.click();expect(page.get_by_role('spinbutton',name='结束日期年份')).to_be_visible()
        end.fill('2020-02-29');end.press('Enter')
        submitted=[]
        # Use an existing strategy identity in the mock save response; do not alter metadata.
        strategy=context.request.get('http://127.0.0.1:7242/api/v2/strategies').json()[0]
        page.route('**/api/v2/strategies',lambda route:route.fulfill(json=strategy) if route.request.method=='POST' else route.continue_())
        def capture(route):
            if route.request.method=='POST':
                submitted.append(route.request.post_data_json)
                route.fulfill(status=400,json={'detail':'DATE_ACCEPTANCE_INTERCEPTED'})
            else:route.continue_()
        page.route('**/api/v2/runs',capture)
        page.get_by_role('button',name='运行回测',exact=True).click()
        expect(page.get_by_text('DATE_ACCEPTANCE_INTERCEPTED',exact=True)).to_be_visible()
        assert submitted[0]['start_date']=='2019-01-01' and submitted[0]['end_date']=='2020-02-29'
        page.locator('.ant-alert-close-icon').click()
        start.click();page.screenshot(path=str(OUT/'calendar.png'),full_page=True)
        assert not errors,errors
        (OUT/'browser.json').write_text(json.dumps({'passed':True,'page_errors':errors,'checks':['2019-01-01 direct input','2019-01-01 year/month jump and calendar click','year/month header and leap day','submitted dates match UI'],'submitted_dates':{k:submitted[0][k] for k in ['start_date','end_date']},'requests_mocked':True},ensure_ascii=False,indent=2),encoding='utf-8')
        browser.close()

if __name__=='__main__':main()
