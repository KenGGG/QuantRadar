# QuantRadar2 Active Phase

Updated: 2026-10-09 (Asia/Shanghai).

**Milestone:** QUANTRADAR2_RESEARCH_WORKBENCH_V1
**Active Goal:** NONE
**Status:** COMPLETE

## Authoritative plan

[开发计划](QUANTRADAR2_DEVELOPMENT_PLAN.md) 的首版 G0 → G1 → G2 已完成。G3 未启动，不是当前目标。

## Accepted gates

- [G0](acceptance/quantradar2-g0/README.md)：源码与环境审查、数据连通和 data-only 服务边界。
- [G1](acceptance/quantradar2-g1/README.md)：SQLite、精简 API、独立回测进程和三个 WebUI 页面。
- [G2](acceptance/quantradar2-g2/README.md)：四组策略冻结回放精确一致、分钟语义、停止/超时/重启、浏览器及 Windows 交付。
- 最终 18 项测试通过；前端构建、依赖一致性检查通过。

## Persistent constraints

SQLite 已授权，应用不开发交易。QMT 正常行情缓存写入已授权；不改 QMT 安装程序/包/策略/配置，不调用真实交易接口，不恢复双 Dolt/DataHub，不新增外部数据源，不改 BulletTrade 引擎，不推送旧仓库 main。

底层既有 Gateway 仍开放交易；V2 使用独立 features=data 服务，不把 Gateway 宣称为全局只读。已知历史数据限制见验收文档；没有自动开启后续修复目标。

## Post-release correction

用户要求的原版聚宽风格恢复及全项目临时文件扫描清理已完成。验收见 [页面恢复与清理](acceptance/quantradar2-ui-cleanup/README.md)。本次修正不启动 G3。
