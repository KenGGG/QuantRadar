# QuantRadar2

Windows 本机、单用户的聚宽风格研究工作台，使用 BulletTrade 原生回测引擎、大QMT 数据及 SQLite 应用元数据。提供策略编辑、修订、日频/分钟模拟回测、日志、原生报告和有限冻结数据回放；暂不开发实盘交易。

访问 http://127.0.0.1:7242/ 。安装、启动和停止步骤见 [运行说明](docs/QUANTRADAR2_RUNBOOK.md)。

- [开发计划](docs/QUANTRADAR2_DEVELOPMENT_PLAN.md)
- [当前阶段](docs/ACTIVE_PHASE.md)
- [系统状态](docs/CURRENT_STATE.md)
- [G0环境与数据验收](docs/acceptance/quantradar2-g0/README.md)
- [G1研究工作台验收](docs/acceptance/quantradar2-g1/README.md)
- [G2首版验收](docs/acceptance/quantradar2-g2/README.md)
- [页面恢复与文件清理](docs/acceptance/quantradar2-ui-cleanup/README.md)

G0–G2已完成，G3未启动。旧版功能代码、文档、vendor和部署配置已移除，历史仅在Git追溯。当前应用无需Dolt/DataHub、Qlib或Kronos。依赖统一由pyproject.toml声明，requirements.lock仅记录已验收完整环境。

数据与回放资格限于已验收场景；历史ST、财务时点、历史成分等限制详见验收文档。策略进程仅面向可信代码，不是恶意Python沙箱。既有底层Gateway仍开放交易，V2使用独立数据专用服务。
