# QuantRadar Active Phase

**Milestone:** `QUANTRADAR_LOCAL_BACKTEST_WEBUI_PASS`
**Active Goal:** `JOINQUANT_LAYOUT_BROWSER_ACCEPTANCE_PASS`
**Completed Goal:** `LOCAL_DAILY_BACKTEST_BROWSER_ACCEPTANCE_PASS`
**Status:** IN_PROGRESS

## 当前布局改版（2026-09-08）

按用户提供的两张聚宽截图调整现有全部 WebUI 的布局与视觉：深蓝横向导航、
策略标题与页签、左源码右参数/收益/日志的编辑工作台，以及左详情导航右指标图表的报告页。
保留 QuantRadar 品牌及现有数据、研报、运行和实验功能；不加入截图中的未支持业务。
复用原生指标和 CSV 展示，不新增指标计算。浏览器复核三个样例、保存重开、
报告后继续编辑、历史恢复、失败提示、各菜单及窄屏布局，保存改版截图与运行证据。
首次操作阻断：本地 7231 端口不可连接；恢复现有服务后继续验收。

## 唯一目标与授权范围

交付聚宽式本地日频回测 WebUI：浏览器管理、编辑和保存策略，配置参数，
使用本地 investment_data 经 InvestmentDataProvider 和 BulletTrade 回测，
查看收益、持仓、成交、日志，并恢复历史源码与配置继续编辑。
解除本目标所需 React、FastAPI、Worker、PostgreSQL、Provider、BulletTrade 开发冻结。
复用现有引擎、任务体系和原生报告，不新增第二套实现或指标计算。

研报保持现有每日运行，只修必要故障。NotebookLM 后续目标暂停；Qlib、Kronos、
新数据源、ETF、实盘及其他扩展不在本轮范围。不得以 Qlib 成熟、全市场数据或
研报七日观察为前置条件，推迟已支持范围的交付。

## 执行与验收门禁

1. 先在本地实际部署版本用浏览器走主流程，记录第一个失败或无法完成的操作。
2. 沿流程逐项修复：保存重开、报告后编辑、历史源码/配置恢复、报告与成功状态
   一致、菜单导航、任务失败提示、页面参数实际生效。
3. 买入持有、双均线、多股票定期再平衡三个样例完成浏览器端到端验收。
4. 保存实际操作路径、部署版本、运行 ID、页面与原生结果证据及不支持范围。
   测试通过、脚本成功或生成报告文件均不能单独判定交付。
5. 达标后更新 CURRENT_STATE 和本文件，提交 commit。里程碑完成后停止。

`LOCAL_DAILY_BACKTEST_BROWSER_ACCEPTANCE_PASS = PASS`

验收日期：2026-09-07。实际部署代码：`5118bd4ec9a082b45eacd0422b40e0452d3124c3`。
三个样例均完成浏览器键盘编辑、保存/刷新重开、配置、真实回测、原生报告、
成交、持仓、日志和历史恢复。另验证改变草稿后恢复重跑结果哈希一致、
菜单导航、故意失败及缺基准失败提示、内置标的/股数/资金/日期实际生效。
证据与限制见 [浏览器交付记录](acceptance/local-backtest/README.md)
和 [运行清单](acceptance/local-backtest/manifest.json)。
上述为上一版主流程证据；当前截图布局改版尚未验收。

## Queued Goals

无。本轮只有上述 Goal；不自动恢复研报、Qlib 或 Kronos 队列。

## 历史状态

此前研报已完成能力与证据保留于 CURRENT_STATE 及历史 Git 文档。
`REPORT_MVP_7D_LIVE_PASS = ABORTED_BY_PROVIDER_CUTOVER` 保持原结论。
NotebookLM 原 `NOTEBOOKLM_POLICY_RUNTIME_PASS` 未验收，暂停而非判定通过。
