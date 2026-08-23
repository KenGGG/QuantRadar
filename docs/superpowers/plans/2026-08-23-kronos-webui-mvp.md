# Kronos WebUI 回测 MVP 实施计划

> 执行约束：本计划经用户确认后，直接在 `main` 上按顺序实施。每项功能先写失败测试，
> 再写最小实现，再运行针对性测试；不创建新 worktree 或功能分支。

**目标：** 在本地 QuantRadar WebUI 中提交、跟踪和查看 Kronos 研究回测，并直接展示
BulletTrade 生成的聚宽风格标准报告及完整报告。

**架构：** FastAPI 进程内使用单线程 `KronosRunManager` 执行现有
`run_research_pipeline()`，以本地 JSON 保存少量任务状态。React 页面只负责参数、状态、
历史与原生 HTML 报告展示，不实现任何回测或绩效计算。

**技术栈：** Python 3.11、FastAPI、ThreadPoolExecutor、React 18、TypeScript、Ant
Design、Vitest、Testing Library、BulletTrade、Kronos 独立 runtime。

---

## Task 1：实现本地任务记录与参数校验

**文件：**

- 新建：`backend/quantradar/kronos/web_runs.py`
- 新建：`tests/unit/kronos/test_web_runs.py`

### 1.1 先写失败测试

覆盖以下行为：

```python
def test_validate_config_accepts_local_mvp_defaults(): ...
def test_validate_config_rejects_invalid_dates_topk_cash_and_universe(): ...
def test_store_round_trips_job_and_lists_newest_first(tmp_path): ...
def test_recover_marks_nonterminal_jobs_failed(tmp_path): ...
```

断言默认参数规范化为：

```python
{
    "start": "2026-08-01",
    "end": "2026-08-18",
    "universe": "all_a_liquid",
    "topk": 20,
    "initial_cash": 1_000_000.0,
}
```

运行并确认失败：

```bash
.venv/bin/python -m pytest tests/unit/kronos/test_web_runs.py -q
```

### 1.2 写最小实现

在 `web_runs.py` 增加：

```python
TERMINAL_STATUSES = {"SUCCESS", "FAILED"}

def validate_kronos_config(payload: Mapping[str, Any], *, latest_date: str) -> dict[str, Any]: ...

class JsonJobStore:
    def create(self, config: Mapping[str, Any]) -> dict[str, Any]: ...
    def save(self, record: Mapping[str, Any]) -> dict[str, Any]: ...
    def get(self, job_id: str) -> dict[str, Any] | None: ...
    def list(self, limit: int = 20) -> list[dict[str, Any]]: ...
    def mark_interrupted_failed(self) -> int: ...
```

实现要求：

- job ID 使用 UUID hex，不接受用户指定目录名；
- 时间使用带时区的 UTC ISO 字符串；
- `job.json` 通过同目录临时文件与 `os.replace()` 写入；
- 只允许四个状态，拒绝无效状态转换；
- 遗留 `PENDING/RUNNING` 的错误写为“本地服务在任务执行前或期间中断，请重新提交”；
- 启动时不自动重跑旧任务，避免用户不知情地占用 GPU。

### 1.3 验证并提交

```bash
.venv/bin/python -m pytest tests/unit/kronos/test_web_runs.py -q
git add backend/quantradar/kronos/web_runs.py tests/unit/kronos/test_web_runs.py
git commit -m "feat(kronos): add local WebUI job store"
```

## Task 2：实现能力预检与单线程执行器

**文件：**

- 修改：`backend/quantradar/kronos/web_runs.py`
- 修改：`tests/unit/kronos/test_web_runs.py`

### 2.1 先写失败测试

新增测试：

```python
def test_capabilities_match_audit_only_at_current_dolt_commit(tmp_path): ...
def test_capabilities_report_missing_runtime_and_contract(tmp_path): ...
def test_manager_calls_pipeline_with_existing_universe_and_parameters(tmp_path): ...
def test_manager_never_runs_two_pipeline_calls_concurrently(tmp_path): ...
def test_manager_records_pipeline_failure_and_traceback(tmp_path): ...
```

fake pipeline 使用 `threading.Event` 阻塞第一个任务，断言第二个任务仍为 `PENDING`；
释放后两者依次完成。

### 2.2 写最小实现

增加：

```python
def kronos_capabilities(provider, *, repo_root: Path) -> dict[str, Any]: ...

class KronosRunManager:
    def submit(self, config: Mapping[str, Any]) -> dict[str, Any]: ...
    def get(self, job_id: str) -> dict[str, Any] | None: ...
    def list(self, limit: int = 20) -> list[dict[str, Any]]: ...
    def shutdown(self) -> None: ...
```

manager 默认路径：

```python
repo_root / "runs/kronos_jobs"
repo_root / "artifacts/kronos/signals"
repo_root / "runs"
```

执行线程调用：

```python
run_research_pipeline(
    provider,
    repo_root=repo_root,
    artifacts_root=artifacts_root,
    runs_dir=runs_dir,
    start=config["start"],
    end=config["end"],
    universe=parse_universe(config["universe"]),
    topk=config["topk"],
    initial_cash=config["initial_cash"],
)
```

能力预检只读取并汇总已有事实：

- `audit.collect_audit_env()` 的 Dolt commit 和最新日期；
- `reports/kronos/data_audit/data_gate.json`；
- `reports/kronos/data_audit/data_contract.json`；
- `models/kronos/kronos_model_lock.json`；
- `.venv-kronos/bin/python` 与 `kronos_runtime/signal_runner.py`。

只有 audit 的 `data_commit` 与当前 Dolt commit 相同时才透传门禁；否则门禁为
`UNKNOWN/BLOCKED` 并附原因。`can_submit` 只在数据日期、contract、model lock 和 runtime
均可用时为真。

### 2.3 验证并提交

```bash
.venv/bin/python -m pytest tests/unit/kronos/test_web_runs.py -q
git add backend/quantradar/kronos/web_runs.py tests/unit/kronos/test_web_runs.py
git commit -m "feat(kronos): execute local WebUI jobs serially"
```

## Task 3：增加 Kronos FastAPI 接口和安全报告服务

**文件：**

- 修改：`backend/quantradar/api/app.py`
- 新建：`tests/unit/kronos/test_web_api.py`

### 3.1 先写失败测试

通过 monkeypatch 注入 fake manager 与 fake capabilities，覆盖：

```python
def test_get_kronos_capabilities(): ...
def test_submit_kronos_run_returns_202(): ...
def test_submit_rejects_unavailable_capability_with_409(): ...
def test_submit_rejects_bad_config_with_422(): ...
def test_list_and_get_kronos_runs(): ...
def test_report_defaults_to_standard_and_can_open_full(tmp_path): ...
def test_artifact_path_cannot_escape_registered_roots(tmp_path): ...
```

报告测试分别写入 `standard_report.html` 与 `report.html`，断言响应为 `text/html` 且
默认返回前者。

### 3.2 写最小实现

在 `app.py` 增加惰性单例：

```python
def _get_kronos_manager() -> KronosRunManager: ...
```

增加接口：

```text
GET  /api/kronos/capabilities
POST /api/kronos/runs
GET  /api/kronos/runs
GET  /api/kronos/runs/{job_id}
GET  /api/kronos/runs/{job_id}/report
GET  /api/kronos/runs/{job_id}/artifacts
GET  /api/kronos/runs/{job_id}/artifacts/{scope}/{name:path}
```

实现约束：

- POST 明确设置 `status_code=202`；
- manager 不存在任务时统一 404；
- 报告只对 `SUCCESS` 开放，默认 `which=standard`；
- `scope` 只允许 `signal` 或 `backtest`；
- 根目录来自成功记录，不接受请求提供绝对路径；
- 用 `candidate.resolve().relative_to(root.resolve())` 验证包含关系；
- 不解析或改写 BulletTrade HTML/CSV/metrics。

### 3.3 验证并提交

```bash
.venv/bin/python -m pytest tests/unit/kronos/test_web_api.py tests/unit/test_api.py -q
git add backend/quantradar/api/app.py tests/unit/kronos/test_web_api.py
git commit -m "feat(api): expose local Kronos backtest runs"
```

## Task 4：建立最小前端组件测试环境和 API 类型

**文件：**

- 修改：`frontend/package.json`
- 修改：`frontend/package-lock.json`
- 修改：`frontend/src/api.ts`
- 新建：`frontend/vitest.config.ts`
- 新建：`frontend/src/test/setup.ts`
- 新建：`frontend/src/api.test.ts`

### 4.1 安装测试依赖并先写失败测试

安装：

```bash
cd frontend
npm install --save-dev vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```

新增脚本：

```json
"test": "vitest run"
```

测试 `submitKronosRun()` 的 URL、方法、JSON body，以及 standard/full URL 的编码。

### 4.2 增加 API 类型和函数

在 `api.ts` 增加：

```typescript
export type KronosStatus = "PENDING" | "RUNNING" | "SUCCESS" | "FAILED";
export interface KronosRunConfig { /* start/end/universe/topk/initial_cash */ }
export interface KronosCapabilities { /* can_submit/reasons/environment/gates/defaults */ }
export interface KronosRunRecord { /* job_id/status/config/times/error/result */ }

export function getKronosCapabilities(): Promise<KronosCapabilities>;
export function submitKronosRun(config: KronosRunConfig): Promise<KronosRunRecord>;
export function listKronosRuns(limit?: number): Promise<{ runs: KronosRunRecord[] }>;
export function getKronosRun(jobId: string): Promise<KronosRunRecord>;
export function getKronosReportUrl(jobId: string, which?: "standard" | "full"): string;
```

### 4.3 验证并提交

```bash
cd frontend && npm test && npm run typecheck
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/test/setup.ts frontend/src/api.ts frontend/src/api.test.ts
git commit -m "test(webui): add Kronos API client coverage"
```

## Task 5：实现 BulletTrade / 聚宽风格 Kronos 页面

**文件：**

- 新建：`frontend/src/components/KronosWorkbench.tsx`
- 新建：`frontend/src/components/KronosWorkbench.test.tsx`
- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/index.css`

### 5.1 先写失败的用户行为测试

mock `frontend/src/api.ts`，覆盖：

```typescript
it("展示能力、数据 commit 和研究级警告", async () => {});
it("提交表单并轮询到 SUCCESS", async () => {});
it("能力不足时禁用提交并显示原因", async () => {});
it("失败任务显示后端错误摘要", async () => {});
it("成功后默认展示聚宽风格报告并可切换完整报告", async () => {});
it("点击历史任务可恢复详情", async () => {});
```

断言默认 iframe 的 `src` 为 `which=standard`，切换后为 `which=full`；测试中不出现
任何收益指标计算函数。

### 5.2 写最小页面实现

使用现有 Ant Design 组件：`Alert`、`Card`、`Form`、`DatePicker.RangePicker`、
`InputNumber`、`Select`、`Button`、`Tag`、`Descriptions`、`Table`、`Tabs`、`Spin`。

交互规则：

- 首屏并行加载 capabilities 与最近 20 条记录；
- 日期上限取 `latest_data_date`，后端仍重复校验；
- 成功提交后立刻显示 `PENDING`；
- `PENDING/RUNNING` 每 1500ms 拉取，组件卸载或终态时清理 timer；
- 成功时 iframe 默认 standard；
- 报告 Tab 切换仅改变 URL；
- 刷新列表不影响当前报告；
- 所有状态显示中文文字与英文状态值；
- 窄屏下卡片单列，报告 iframe 最小高度 720px。

在 `App.tsx` 增加菜单项：

```tsx
{ key: "kronos", icon: <LineChartOutlined />, label: "Kronos 回测" }
```

并渲染 `<KronosWorkbench />`。

### 5.3 验证并提交

```bash
cd frontend && npm test && npm run build
git add frontend/src/components/KronosWorkbench.tsx frontend/src/components/KronosWorkbench.test.tsx frontend/src/App.tsx frontend/src/index.css
git commit -m "feat(webui): add Kronos research backtest workspace"
```

## Task 6：补齐本地启动入口、说明和端到端验证

**文件：**

- 修改：`Makefile`
- 修改：`README.md`
- 修改：`docs/CURRENT_STATE.md`
- 修改：`tests/unit/test_web_workbench.py`

### 6.1 先写失败测试

在 `test_web_workbench.py` 增加构建产物契约测试，确认 React 源码含“Kronos 回测”，
API 路由存在，且静态首页仍由 FastAPI 正常托管。

### 6.2 增加简单本地命令和操作说明

Makefile 增加：

```make
web-build:
	cd frontend && $(NPM) run build
```

README 写明本地操作：

```bash
make web-build
make dev
# 打开 http://127.0.0.1:7231 -> Kronos 回测
```

同时说明：修改前端后必须重新 `make web-build`，浏览器必要时强制刷新；这是 FastAPI
托管 `frontend/dist` 的本地部署方式。记录 runtime 缺失时先执行
`make kronos-runtime-setup`，数据审计需要时执行 `make kronos-data-audit`。

### 6.3 全量验证

```bash
.venv/bin/python -m pytest tests/unit -q
cd frontend && npm test && npm run typecheck && npm run build
git diff --check
git status --short
```

若本机 Dolt、Kronos runtime 和 CUDA 就绪，再执行最小真实验证：

```bash
make kronos-research-pipeline START=2026-08-01 END=2026-08-08 TOPK=5
make web-build
make dev
```

通过 API 提交同一小区间，确认状态到 `SUCCESS`，并人工打开聚宽风格及完整报告。
如本地数据最新日期早于示例日期，改用 capabilities 返回日期内最近两个周信号日。

### 6.4 最终提交

```bash
git add Makefile README.md docs/CURRENT_STATE.md tests/unit/test_web_workbench.py
git commit -m "docs: document local Kronos WebUI workflow"
```

## 实施完成检查表

- [ ] 所有变更都在 `main`，未创建支线或 worktree。
- [ ] Kronos GPU 任务严格串行。
- [ ] 本地 JSON 状态可在页面刷新后读取。
- [ ] 默认展示 BulletTrade 生成的聚宽风格 `standard_report.html`。
- [ ] 可切换 BulletTrade 原生 `report.html`。
- [ ] API/前端没有重算任何绩效指标。
- [ ] audit gate 只在 Dolt commit 匹配时生效。
- [ ] 路径穿越测试通过。
- [ ] 后端单元测试、前端测试、类型检查和 production build 全部通过。
- [ ] README 明确了 `make web-build && make dev`，避免 WebUI 仍显示旧构建。
