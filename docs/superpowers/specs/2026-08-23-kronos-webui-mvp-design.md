# Kronos WebUI 回测 MVP 规格

## 1. 决策摘要

本项目只面向本地部署，后续功能直接在 `main` 开发。现有
`feat/kronos-gate-refactor` 与 `feat/kronos-webui-mvp` 的有效提交已线性并入
`main`；不为本 MVP 引入 PostgreSQL、Redis、消息队列、分布式锁、多进程协调或
独立微服务。

WebUI 提供一条清晰的研究回测路径：

```text
填写参数 -> 本地后台执行 Kronos -> TopK 目标权重
         -> BulletTrade 撮合和绩效 -> 聚宽风格报告（默认）
         -> BulletTrade 完整报告（可切换）
```

MVP 只支持单次提交、串行执行、状态查看、最近记录和报告浏览。不支持参数矩阵、
任务取消、断点调度、多用户权限、远程部署或实盘交易。

## 2. 产品体验

侧边栏新增“**Kronos 回测**”。页面保持现有 React、TypeScript、Ant Design 风格，
不增加第二套 UI 框架。

页面从上到下只有四块：

1. **研究状态**：当前 Dolt commit、最新行情日期、Kronos runtime/model lock、研究/
   真实/正式门禁及 fidelity。状态必须同时显示文字，不能只靠颜色。
2. **回测参数**：开始日期、结束日期、Universe、TopK、初始资金；同时展示固定的
   90 日 lookback、10 日预测、5 个 seed、周频信号和 T+1 执行。
3. **本次运行**：`PENDING/RUNNING/SUCCESS/FAILED`、运行 ID、时间与错误摘要；
   运行时每 1.5 秒轮询，终态停止。
4. **最近记录与报告**：默认打开 BulletTrade 的 `standard_report.html`，标题为
   “聚宽风格报告”；可切换原生 `report.html`，标题为“BulletTrade 完整报告”。

所有页面固定显示“研究级结果，不构成投资建议”。当
`formal_backtest_ready=false` 时，不得使用“正式回测通过”等措辞。

## 3. BulletTrade / 聚宽风格边界

- `run_research_pipeline()` 仍是唯一 Kronos 研究闭环入口。
- `run_unified_target_weight_backtest()` 仍是唯一目标权重回测入口。
- 撮合、账户、订单、佣金、滑点、成交、持仓、指标与报告均由 BulletTrade 产生。
- API 和前端不得重算收益率、年化、夏普、最大回撤、胜率、盈亏比或净值曲线。
- 聚宽风格来自 BulletTrade `generate_cli_report()` 生成的
  `standard_report.html`，不是前端仿制。
- 完整视图直接展示 BulletTrade `generate_report()` 生成的 `report.html`。
- Universe 使用现有 `parse_universe()`，默认 `all_a_liquid`，不复制门禁或 PIT 逻辑。

## 4. 本地任务模型

新增一个轻量 `KronosRunManager`：

- 进程内 `ThreadPoolExecutor(max_workers=1)`，保证只运行一个 GPU 任务；
- 任务状态写入 `runs/kronos_jobs/<job_id>/job.json`；
- 完整异常写入同目录 `runner.log`，页面只显示截断摘要；
- 大型 Signal/Parquet/HTML 继续留在既有 artifact 与 BulletTrade run 目录，不复制；
- 服务启动时把遗留 `PENDING/RUNNING` 标为 `FAILED`，说明服务曾中断；用户可重新提交；
- 不实现复杂的自动重放、跨进程锁或分布式恢复。

状态机：

```text
PENDING -> RUNNING -> SUCCESS
                   -> FAILED
```

JSON 使用临时文件加 `os.replace()` 原子写入。写入 `SUCCESS` 前必须先记录 pipeline
返回的 signal 目录、backtest run 目录、manifest 和 gate。

## 5. API

在现有 FastAPI 应用中增加：

```text
GET  /api/kronos/capabilities
POST /api/kronos/runs
GET  /api/kronos/runs?limit=20
GET  /api/kronos/runs/{job_id}
GET  /api/kronos/runs/{job_id}/report?which=standard|full
GET  /api/kronos/runs/{job_id}/artifacts
GET  /api/kronos/runs/{job_id}/artifacts/{scope}/{name:path}
```

提交参数：

```json
{
  "start": "2026-08-01",
  "end": "2026-08-18",
  "universe": "all_a_liquid",
  "topk": 20,
  "initial_cash": 1000000
}
```

校验：日期为 ISO 格式且 `start <= end`，`end` 不晚于最新行情日期，`topk` 为
1–100，初始资金不少于 10,000，Universe 必须受现有解析器支持。缺少 data
contract、model lock、独立 Kronos runtime 或可用数据时，能力接口返回原因，提交
返回 409；字段错误返回 422。

`capabilities` 直接汇总当前环境和同一 Dolt commit 的 audit gate。缺失、损坏或
commit 不匹配的 gate 一律保守显示为不可用，不推导新的门禁结论。

报告和产物接口只允许访问成功任务记录中登记的 `signal_run_dir` 和
`backtest.run_dir`。使用 `Path.resolve()` 与 `Path.relative_to()` 校验路径，拒绝
目录穿越；HTML 用 `FileResponse` 原样内联返回。

## 6. 代码组织

```text
backend/quantradar/kronos/web_runs.py     # 参数、JSON 状态、串行执行、能力汇总
backend/quantradar/api/app.py             # Kronos HTTP 接口与安全文件响应
frontend/src/api.ts                       # API 类型和请求函数
frontend/src/components/KronosWorkbench.tsx
frontend/src/App.tsx                      # 菜单入口
```

MVP 使用一个前端组件承载表单、状态、历史与报告，避免提前拆出复杂状态管理层。
后端 manager 接受可注入的 provider、pipeline 和 executor，便于无需 GPU/Dolt 的单元
测试。

## 7. 测试与验收

后端测试覆盖：

- 参数边界和能力预检；
- JSON 原子状态、串行队列、成功与失败；
- 服务重启后的遗留 `PENDING/RUNNING -> FAILED`；
- 202/409/404/422 接口语义；
- standard/full 报告与目录穿越拒绝；
- pipeline 调用参数确实使用默认 `all_a_liquid` 和用户 TopK/资金。

前端引入最小 Vitest + Testing Library，覆盖能力展示、表单提交、状态轮询、失败
提示、默认聚宽风格报告、完整报告切换和研究级警告。

完成标准：

- 本地 `make dev` 后可在 WebUI 提交 Kronos 回测；
- 两个提交不会并发占用 GPU；
- 刷新页面仍可查看落盘的最近任务；
- 成功任务能直接浏览两个 BulletTrade 原生 HTML 报告；
- 页面与 API 不存在绩效重算；
- 无 Dolt/GPU 的普通 CI 使用 fake 依赖通过，显式 live smoke 在条件不足时跳过；
- TypeScript、Vite production build 与后端单元测试通过。

## 8. 非目标

PostgreSQL 任务表、多 worker、多用户、远程队列、任务取消、自动重试、参数扫描、
实验比较、模型训练和实盘接入均不属于本 MVP。只有实际使用出现需求后再增加，
不提前设计。
