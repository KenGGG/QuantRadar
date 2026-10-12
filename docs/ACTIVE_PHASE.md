# QuantRadar2 Active Phase

Updated: 2026-10-12 (Asia/Shanghai).

**Milestone:** QUANTRADAR2_RESEARCH_WORKBENCH_V1
**Active Goal:** JOINQUANT_PRICE_AND_METRIC_ALIGNMENT
**Status:** VERIFIED_FIXES_AWAITING_JOINQUANT_EXPORTS

新增用户聚宽position.zip核对：1681日权益还原740.366924%，年化/Sharpe/Alpha/Beta/IR/回撤重算与截图一致；Sortino同序列1.846不同于1.691，尚未对齐。首个收盘价差异为2019-10-11的512890（0.562/0.575）。见[position export](acceptance/quantradar2-jq-alignment/position-export.md)。

按用户提供API定义修正价格模式和风险指标；使用修正版聚宽日志逐日对齐原策略，保留严格缓存、原修订和旧产物。不修改外部BulletTrade安装。

默认前复权撮合/估值、半档舍入、精确费用及成交量限制已修复；相关应用指标及导出已更新。ec853550完整1681日及f56ac7b3回放成功，8CSV一致，真实浏览器导出验证通过。194笔成交与聚宽相同，错误拒单为0，但779.15%仍不同于740.37%；4日信号差异和首次2019-10-11行情差异已定位。用户已询问数据导出方式，诊断版生成原始行情及每日权益两CSV。等待这些数据后继续同一目标，不能标记完成或启动其他目标。见[阶段验收](acceptance/quantradar2-jq-alignment/README.md)。

修复用户原样聚宽修正版在QuantRadar失败：自动规划支持明确导入builtins的max/min别名，保留缓存语义校验，真实全区间回测验证。

56项测试通过，原失败任务同一修订新任务63e263c6完整1681日SUCCEEDED约38.48秒，自动84根窗口并命中缓存；API已加载修复。见[验收](acceptance/quantradar2-builtins-plan/README.md)。未修复跨平台收益/撮合/指标差异；无排队目标。

用户明确授权修复粘贴的聚宽源码。交付独立修正版，显式绑定Python内置any/max，验证NumPy同名函数遮蔽时空仓买入及清仓保护，不改平台源码、行情、价格模式或既有策略修订。

examples/v2/etf_three_factor_joinquant_fixed.py已交付；4项定向测试通过，覆盖空仓买入、未完成清仓保护、完成清仓后换仓及未来行情/平分规则。没有在聚宽实际重跑，不宣称收益与本地相同；本地撮合及指标问题仍为已发现、尚未修复的独立问题。无排队目标。

2026-10-12 用户要求不改聚宽策略源码、无需手工数据声明，由系统自动识别数据需求并完成缓存准备。保留先缓存再计算及禁止在线回退。

无声明ETF原修订全区间1681日首次/缓存复用均成功，约124.63/43.28秒；8份CSV和金融指标一致，源码及修订未修改。51项测试、类型/构建和浏览器无数据清单提交通过。新版API已加载。见[无感自动准备验收](acceptance/quantradar2-transparent-cache/README.md)。无排队目标，G3未启动。

下列为此前完成的升级验收。数据模式以上方无感自动准备为准，不再要求用户提供数据声明。

45项后端测试、类型检查、生产构建及浏览器请求验收通过。网页已只提交prepared；后端完整加载由scripts/v2_restart_when_idle.py在队列清空后执行，加载结果见var/quantradar2/mandatory-deployment.json。旧任务被既有超时机制结束后队列清空，新后端已加载；实际API验证四种旧模式名称均无法绕过数据清单校验。无排队目标。见[验收](acceptance/quantradar2-mandatory-cache/README.md)。

新策略默认自动数据模式：固定证券池日频使用预准备，否则查询并记录；显式预准备严格验证并给出中文提示。45项测试、构建及网页模式/请求检查通过，API已加载新版，见[自动模式验收](acceptance/quantradar2-auto-mode/README.md)。

历史日期控件已提供中文年月及显式年/月跳转。2019-01-01输入/日历选择、闰日与提交参数一致性浏览器验收及生产构建通过；见[历史日期验收](acceptance/quantradar2-dates/README.md)。没有新增回测或修改策略。

策略列表已作为默认首页，提供显著的新建空白策略、搜索、打开编辑、跨修订历史回测数量/入口及复制/归档/恢复。真正空白源码可保存，空代码不启动任务。44项测试、类型/构建及创建-编辑-保存-搜索-历史/手机浏览器验收通过，API已重新加载；见[策略列表验收](acceptance/quantradar2-strategy-list/README.md)。

用户授权的应用层完整指标与1/3/6/12月滚动表、聚宽式双栏编辑/结果/日志已完成。43项测试、计算边界测试、CSV检查、类型检查、生产构建及真实回测桌面/手机浏览器验收通过，见[指标与编辑器验收](acceptance/quantradar2-metrics-editor/README.md)。原生报告及历史产物不变，G3未启动。

回测详情已按用户提供的聚宽截图升级：独立详情页、顶部设置状态、左侧栏目、原生指标网格、收益/盈亏/持仓图、交易和每日持仓表、日志、阶段性能、不可变历史源码及原生月度收益。缺失指标和滚动序列明确提示，不重算原生指标。43项测试、CSV边界检查、类型检查、生产构建及真实完整回测桌面/手机浏览器验收通过，见[详情验收](acceptance/quantradar2-details/README.md)。G3未启动。

## Completed upgrade

USER_AUTHORIZED_QMT_LOCAL_DATA_PREPARATION已完成：应用层固定证券池日频预准备、可复用缓存、独立校验快照及纯本地回测，涵盖日历、行情、按历史日期证券信息及权益事件。原ETF三因子修订完整1681日首次/复用/回放三任务成功；8份CSV和金融指标一致，旧5053fab2已有1147日权益与1051日因子/选择一致。43项测试、前端构建与依赖检查通过，API已运行升级版本。见[预准备验收](acceptance/quantradar2-data-preparation/README.md)。

此前日历适配因1800秒时限受阻；本次沿用其应用适配，原修订/参数/参考日完成全区间原生报告，保留96日现金warmup和原生基准口径，不修改旧失败任务或重算指标。本次按AGENTS协议本地提交升级及必要日历依赖；不推送。QMT、外部引擎和交易接口不变，未新增外部数据源。

## Authoritative plan

[开发计划](QUANTRADAR2_DEVELOPMENT_PLAN.md) 的首版 G0 → G1 → G2 已完成。G3 未启动，不是当前目标。

## Accepted gates

- [G0](acceptance/quantradar2-g0/README.md)：源码与环境审查、数据连通和 data-only 服务边界。
- [G1](acceptance/quantradar2-g1/README.md)：SQLite、精简 API、独立回测进程和三个 WebUI 页面。
- [G2](acceptance/quantradar2-g2/README.md)：四组策略冻结回放精确一致、分钟语义、停止/超时/重启、浏览器及 Windows 交付。
- 首版 18 项测试通过；本次升级后当前43项测试通过，前端构建、依赖一致性检查通过。

## Persistent constraints

SQLite 已授权，应用不开发交易。QMT 正常行情缓存写入已授权；不改 QMT 安装程序/包/策略/配置，不调用真实交易接口，不恢复双 Dolt/DataHub，不新增外部数据源，不改 BulletTrade 引擎，不推送旧仓库 main。

底层既有 Gateway 仍开放交易；V2 使用独立 features=data 服务，不把 Gateway 宣称为全局只读。已知历史数据限制见验收文档；没有自动开启后续修复目标。

## Post-release correction

用户要求的原版聚宽风格恢复及全项目临时文件扫描清理已完成。验收见 [页面恢复与清理](acceptance/quantradar2-ui-cleanup/README.md)。本次修正不启动 G3。

用户要求的 docs 清理已完成：旧 QuantRadar 开发资料删除，仅保留本次 QuantRadar2 主文档及验收，G3未启动。

旧功能代码专项清理已完成，当前仅V2运行/构建/测试链路；[记录](acceptance/quantradar2-ui-cleanup/code-pruning.md)。G3未启动。
