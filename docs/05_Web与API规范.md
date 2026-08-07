# Web 与 API 规范

文件：`docs/05_Web与API规范.md`

本文件仅在进入 **Web 阶段（Phase 7 / Phase 8）** 时才需要读取。

基础设施与目录见 `02`，回测运行见 `04`。

---

# 一、服务化分层（Phase 7）

```text
PostgreSQL  —— 工作流元数据（Strategy / Backtest Run / Experiment）
FastAPI     —— 所有功能先通过 API 暴露
Worker      —— 异步执行回测 / 实验（见 02 第九节）
```

```text
禁止：在研究主线早期引入 Web / DB
禁止：Web 直接调用 BulletTrade 内部，必须经由 API
```

PostgreSQL 只存元数据，不存行情事实（事实源仍是 investment_data，见 03）。

---

# 二、PostgreSQL 表（约定，待 Phase 7 落地确认）

```text
strategies       策略定义（id, name, code_ref, created_at）
backtest_runs    回测运行（id, strategy_id, config_hash, run_id, status）
experiments      实验（id, name, runs[], metrics, snapshot_ref）
data_status      数据覆盖与 BLOCKED 状态（来自 Provider Acceptance）
```

真实 schema 以 Phase 7 实现与 CURRENT_STATE 记录为准。

---

# 三、API 约定

```text
所有接口经 FastAPI，返回 JSON
认证：本地优先，轻量（研究平台，非公网 SaaS）
错误：明确返回 BLOCKED / FAILED 状态，不吞异常（见 00 第四节）
回测提交 → Worker 执行 → 轮询/回调结果
```

---

# 四、前端技术栈

```text
框架：React
语言：TypeScript
组件库：Ant Design
代码编辑器：Monaco（策略编辑）
图表：ECharts（NAV / 净值 / 指标）
```

```text
禁止：在 Web 阶段前引入前端依赖
界面语言：中文
```

---

# 五、导航与页面

## 5.1 导航

```text
首页 / 策略编辑器 / 回测 / 实验 / 数据中心
```

## 5.2 首页

```text
项目概览、最近运行、数据状态摘要
```

## 5.3 策略编辑器

```text
Monaco 编辑策略源码
支持 from jqdata import * 兼容写法（见 Phase 3）
保存为 strategies 记录
```

## 5.4 回测页面

```text
选择策略 + 配置 → 发起回测（经 API → Worker）
展示 NAV / Position / Trade / Metrics（来自 04 的 Run 目录）
```

## 5.5 实验页面

```text
管理 Experiment，比较多次回测 Snapshot（见 04）
```

## 5.6 数据中心

```text
展示 investment_data 覆盖与 BLOCKED 状态（来自 Provider Acceptance，见 03）
明确标出缺失能力，不伪造成功
```

---

# 六、与其他文档关系

```text
02 架构：PostgreSQL / Worker / 目录
04 回测：Run 目录、Snapshot、Manifest 是 Web 展示的数据源
03 数据：数据中心页展示 Provider Acceptance 状态
```
