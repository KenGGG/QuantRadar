# QuantRadar2 Active Phase

Updated: 2026-10-11 (Asia/Shanghai).

**Milestone:** QUANTRADAR2_RESEARCH_WORKBENCH_V1
**Active Goal:** NONE
**Status:** COMPLETE（用户授权的QMT本地预准备升级通过；G3未启动，无后续排队目标）

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
