# QuantRadar2 Active Phase

Updated: 2026-10-11 (Asia/Shanghai).

**Milestone:** QUANTRADAR2_RESEARCH_WORKBENCH_V1
**Active Goal:** NONE
**Status:** COMPLETE（历史日期选择修正已验收，无排队目标）

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
