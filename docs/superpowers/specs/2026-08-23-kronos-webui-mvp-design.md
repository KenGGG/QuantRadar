# Kronos WebUI 回测 MVP 设计

## 1. 目标与范围

本功能在 QuantRadar WebUI 中提供可操作的 Kronos 研究级回测入口，使用户无需命令行即可完成：

```text
参数配置
  -> 异步生成 Kronos 信号
  -> TopK 目标权重
  -> BulletTrade 统一回测
  -> 聚宽风格标准报告 / BulletTrade 完整报告
  -> 门禁、数据版本与产物审计
```

MVP 支持单次实验提交、持久化运行状态、历史运行列表、运行详情和报告查看。不包含参数矩阵、批量实验、横向指标排名、模型微调、任务取消或实盘交易；这些属于后续 Goal 4 或更高阶段。

本功能的代码实现以前置 PR #2（`feat/kronos-gate-refactor`，至少包含 `b2dab53`）已合并到 `main` 为前提。开始写代码前，`feat/kronos-webui-mvp` 必须同步合并后的 `main`，不得复制或重新实现 PR #2 的 universe、gate 或 Dolt commit 逻辑。

## 2. 不变约束

- WebUI 只调用 FastAPI，不直接连接 Dolt、不加载 Kronos 模型、不调用 BulletTrade 内部对象。
- Kronos 推理继续由 `.venv-kronos` 子进程执行；QuantRadar 主环境不得导入 Torch。
- 回测必须继续使用现有 `run_research_pipeline` 与 `run_unified_target_weight_backtest`。
- 撮合、账户、订单、成本、指标和报告全部来自 BulletTrade；前后端不得重新计算收益率、夏普、回撤、胜率、盈亏比或成交结果。
- 默认报告为 BulletTrade `generate_cli_report()` 生成的 `standard_report.html`（聚宽风格）；同时提供 `generate_report()` 生成的 `report.html`（完整报告）。
- 所有研究结果明确标记为 `research_only`。`formal_backtest_ready=false` 时不得显示“正式回测通过”或投资建议。
- 一次任务开始到结束必须绑定同一 Dolt commit；审计 gate 仅在 commit 匹配时有效。
- 第一版只允许单个 Kronos GPU 任务同时运行，避免并发推理争抢显存。

## 3. 方案选择

### 采用：独立 Kronos 任务管理器 + 文件化任务状态

新增 `KronosRunManager`，内部使用 `ThreadPoolExecutor(max_workers=1)` 调用现有研究流水线。每次提交立即写入原子 JSON 任务记录，再进入单线程队列。Kronos pipeline 自身继续负责 Signal Artifact 的增量恢复和哈希校验。

任务状态保存到：

```text
runs/kronos_jobs/<job_id>/
├── job.json
└── runner.log
```

`job.json` 只保存参数、状态、时间、错误摘要，以及 pipeline 返回的 signal/backtest 路径、manifest 和 gate。预测数组、Parquet、CSV 与 HTML 仍保存在现有 Signal Artifact 和 BulletTrade run 目录中，不复制大文件。

选择文件状态而不是扩展现有 PostgreSQL `BacktestWorker`，原因是：Kronos 是串行 GPU 长任务，现有 Worker 是四线程普通策略回测；强行混用会引入任务类型分支、显存并发和 PostgreSQL 强依赖。MVP 是单机研究工具，原子 JSON 与现有 artifact 边界一致，也能在未配置 PostgreSQL 时使用。

进程启动后，管理器扫描 `PENDING`/`RUNNING` 任务并恢复为 `PENDING` 后重新入队。恢复继续使用同一 `job_id` 和参数，依靠 Signal Artifact 校验跳过已经完成的周分区。单 uvicorn 进程是明确约束；多进程协调不在 MVP 范围。

### 未采用的方案

- **扩展通用 `BacktestWorker`**：可复用 PostgreSQL 状态表，但会把 GPU 串行任务与普通 CPU 回测混在四线程池中，并扩大现有数据模型。
- **HTTP 请求内同步执行**：实现最少，但长时间 GPU 推理会阻塞请求，页面刷新或网络断开后无法可靠追踪状态。

## 4. 后端组件

### 4.1 `backend/quantradar/kronos/web_runs.py`

负责参数验证、任务持久化、单并发执行、恢复与查询，不包含模型或回测计算。

核心类型与接口：

```python
class KronosRunManager:
    def submit(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get(self, job_id: str) -> dict[str, Any] | None: ...
    def list(self, limit: int = 50) -> list[dict[str, Any]]: ...
    def recover(self) -> int: ...
    def wait(self, job_id: str, timeout: float = 300.0) -> None: ...

def get_kronos_run_manager() -> KronosRunManager: ...
def kronos_capabilities(provider, repo_root: Path) -> dict[str, Any]: ...
```

任务参数：

```json
{
  "start": "2026-08-01",
  "end": "2026-08-18",
  "topk": 20,
  "initial_cash": 1000000,
  "universe": "all_a_liquid"
}
```

校验规则：

- `start`、`end` 必须是 ISO 日期，且 `start <= end`；
- `end` 不得晚于最新行情日期；
- `topk` 为 1–100；
- `initial_cash` 至少 10,000；
- `universe` 必须通过 `parse_universe()`；默认 `all_a_liquid`；
- repo 中必须存在 data contract、model lock 和独立 Kronos runtime 入口；缺失时返回清晰的预检错误。

运行时调用：

```python
run_research_pipeline(
    provider,
    repo_root=repo_root,
    artifacts_root=artifacts_root,
    runs_dir=runs_dir,
    start=payload["start"],
    end=payload["end"],
    topk=payload["topk"],
    initial_cash=payload["initial_cash"],
    universe=parse_universe(payload["universe"]),
)
```

状态机只有：

```text
PENDING -> RUNNING -> SUCCESS
                   -> FAILED
```

任何异常都写入 `FAILED` 和截断后的错误摘要；完整 traceback 写入 `runner.log`。写 `SUCCESS` 前必须先持久化 pipeline 结果，确保页面不会看到没有报告路径的成功状态。

### 4.2 能力预检

`kronos_capabilities()` 返回：

- 当前 Dolt commit 和最新行情日期；
- audit gate 的 `data_commit` 及是否匹配当前 commit；
- `kronos_signal_research_ready`、`research_backtest_ready`、`realistic_backtest_ready`、`formal_backtest_ready`、`real_assist_data_ready` 和 fidelity；
- runtime/model lock 是否存在；
- 支持的 universe 和默认参数；
- `can_submit` 及不可提交原因。

缺失或 commit 不匹配的 audit gate 不得被显示为 PASS。研究任务是否可提交由可构造的价格输入、最新行情日期和 runtime 文件决定；审计不匹配会醒目告警，并将 realistic/formal/real-assist 状态保守显示为不可用，但不重新把 Kronos OHLC 信号研究绑死到 CSI PIT。

### 4.3 FastAPI

新增接口：

```text
GET  /api/kronos/capabilities
POST /api/kronos/runs
GET  /api/kronos/runs?limit=50
GET  /api/kronos/runs/{job_id}
GET  /api/kronos/runs/{job_id}/report?which=standard|full
GET  /api/kronos/runs/{job_id}/artifacts
GET  /api/kronos/runs/{job_id}/artifacts/{scope}/{name:path}
```

`POST` 返回 `202 Accepted` 和 `{job_id, status, config}`。参数错误返回 422，能力预检失败返回 409，未知任务/产物返回 404。

报告与产物下载只能访问成功任务记录中声明的 `backtest.run_dir` 或 `signal_run_dir`，必须使用 `Path.resolve()` 校验目标仍位于允许根目录下，阻止目录穿越。HTML 使用 `FileResponse` 原样返回，绝不在 API 层改写指标。

## 5. WebUI

### 5.1 导航与布局

侧边栏新增“**Kronos 研究**”入口。沿用现有 React、TypeScript、Ant Design 和响应式栅格，不引入 Tailwind 或第二套组件库。

页面由四个区域组成：

1. **能力与门禁条**：用状态 Tag 展示研究、研究回测、真实回测、正式回测、实盘辅助；显示当前/audit Dolt commit 是否一致。
2. **实验参数卡**：开始/结束日期、universe、TopK、初始资金，以及固定只读信息（90 日 lookback、10 日预测、5 个固定 seed、周度 T+1）。
3. **运行状态卡**：显示 PENDING/RUNNING/SUCCESS/FAILED、job ID、提交/开始/完成时间和错误；每 1.5 秒轮询，终态停止。
4. **历史运行与结果**：列出最近任务；打开成功任务后默认嵌入聚宽风格报告，可切换 BulletTrade 完整报告，并展示审计 manifest 与产物列表。

提交按钮只有在 `can_submit=true`、表单有效且当前没有重复提交请求时可用。运行中允许浏览其他历史任务，但 MVP 不提供取消按钮。

### 5.2 报告风格

默认 Tab 为“聚宽风格”，iframe 地址使用：

```text
/api/kronos/runs/{job_id}/report?which=standard
```

第二个 Tab 为“BulletTrade 完整报告”，使用 `which=full`。页面不读取 CSV 后自行画净值、回撤或热力图，也不从 snapshot 的简化 metrics 替代 BulletTrade `metrics.json`。

报告上方固定显示“研究级结果”提示。若 `formal_backtest_ready=false`，显示黄色警告：“当前结果为研究级/部分保真，不代表正式高保真回测或投资建议。”

### 5.3 API 客户端类型

`frontend/src/api.ts` 新增 `KronosCapabilities`、`KronosRunConfig`、`KronosRunRecord`、`KronosArtifact`，以及 capabilities、submit、list、get、report URL 和 artifact URL 函数。所有未知后端字段保持可扩展，不在前端重新推导 gate。

## 6. 可访问性与交互

- 所有表单字段有可见标签，错误信息与字段关联；状态不只依赖颜色，同时显示 PASS/PARTIAL/BLOCKED/UNKNOWN 文本。
- iframe 必须设置明确 `title`；运行状态变化通过可见文字和 Ant Design Alert 呈现。
- 窄屏下参数、状态、历史列表纵向排列；桌面端使用左右分栏。
- 日期上限使用 capabilities 返回的最新行情日期，同时后端重复校验。
- 轮询失败显示非阻断提示并允许手动刷新，不把瞬时网络失败误写成任务失败。

## 7. 测试策略

### 后端

- `KronosRunManager` 使用注入的同步 fake executor、fake provider 和 fake pipeline 测试，无需 Dolt/GPU。
- 覆盖参数边界、单并发提交、原子状态、成功结果、失败 traceback、列表排序和重启恢复。
- 能力测试覆盖 audit commit 匹配、缺失、损坏和不匹配。
- API 测试覆盖 202/422/409/404、轮询状态、standard/full 报告、产物列表和目录穿越拒绝。
- 一个带 `requires_dolt + requires_kronos + requires_cuda` 的显式 live smoke 验证真实单周任务；普通 CI 自动跳过。

### 前端

引入 Vitest、Testing Library 和 jsdom，仅用于组件行为测试。覆盖：

- capabilities 加载与 gate 文本；
- 合法表单提交和 payload；
- 无能力/非法日期时禁用；
- PENDING/RUNNING 轮询到 SUCCESS；
- FAILED 错误展示；
- 默认 standard 报告及 full 切换；
- `formal_backtest_ready=false` 的研究级警告。

最终验证包括 backend 全套单元测试、前端测试、TypeScript 检查、Vite production build，以及真实环境单周 smoke（若本机 Dolt、CUDA 和锁定 runtime 可用）。

## 8. 验收标准

- 用户可以在 WebUI 提交一次 `all_a_liquid` Kronos 研究回测并观察完整状态变化。
- 页面刷新后仍能从文件化任务记录恢复并查看历史任务。
- 同一进程不会并发执行两个 Kronos GPU 任务。
- 成功任务能打开聚宽风格标准报告和 BulletTrade 完整报告。
- 页面展示当前 Dolt commit、audit commit 匹配状态、研究/真实/正式/实盘辅助门禁和 fidelity。
- 所有报告指标与交易结果均来自 BulletTrade 原生产物；代码中不存在 WebUI 或 API 重算绩效指标的实现。
- 非正式门禁状态有明确研究限定，不把 PARTIAL realistic 宣称为 formal。
- 产物下载无法越过已登记的 signal/backtest 目录。
- CI 在无 Dolt/GPU 时全绿，真实 live 测试正确 skip；具备本机条件时单周 smoke 通过。
