# Kronos Investment Workbench Goal 2 Design

日期：2026-08-21  
产品需求：`docs/KRONOS_INVESTMENT_WORKBENCH_PRD_v1.md`

## 1. 范围

本设计实现一个研究级端到端闭环：固定 Kronos-base 从历史 PIT 输入生成周度信号，信号转换成 TopK 等权目标仓位，再由现有 BulletTrade 统一回测链生成原生报告。

本阶段不实现 WebUI、数据库任务队列、参数搜索、模型微调、Shadow Mode、实盘交易或外部补充数据 ETL。

## 2. 选择的方案

采用“独立推理、主进程编排、复用回测”的方案：

- `kronos_runtime/signal_runner.py` 在 `.venv-kronos` 中加载固定模型并只负责 GPU 推理；
- `backend/quantradar/kronos/signal/` 在主环境负责 PIT 输入、输出统计、分区存储、恢复和 manifest；
- `backend/quantradar/kronos/portfolio.py` 只负责信号到 Target Weight 的纯转换；
- 现有 Target Weight 桥接抽取为可配置调仓频率的通用实现，Qlib 保持原有月度默认，Kronos 使用周度；
- 端到端编排调用现有 `run_unified_backtest`，不重算 BulletTrade 指标或报告。

未选择让 QuantRadar 主进程直接加载 Kronos，因为这会污染已隔离并通过验收的运行环境。未选择独立实现 Kronos 回测器，因为这会重复 BulletTrade 的职责并破坏现有架构边界。

## 3. 组件边界

### 3.1 输入构建

`backend/quantradar/kronos/signal/inputs.py`：

- 枚举 `000300.SH` 现有 PIT 覆盖内的周度信号日；
- 使用 `signal_date` 当时可见的成分股；
- 使用 Goal 0 已确认的连续研究价格口径构建 90 日 OHLCVA；
- 复用 Goal 1 的资格筛选规则；
- 计算下一交易日 `execution_date` 和后续 10 个交易日标签日期；
- 输出与 Goal 1 兼容的 NPZ 和 `input_manifest.json`。

单次 SignalRun 开始时记录 Dolt HEAD；每个分区和运行结束时重新检查。HEAD 变化立即停止，未完成分区保持未完成状态。

### 3.2 GPU 预测

`kronos_runtime/signal_runner.py` 接收一个周分区，使用 Goal 1 固定的五个 seed。每条路径输出形状为 `[symbols, 10, 6]` 的 float32 预测。它原子写入 `predictions.npz` 和只包含运行环境、批大小、耗时、seed、输入哈希及预测哈希的 JSON 结果。

OOM 处理复用 Goal 1 的批大小减半逻辑；CPU fallback、模型替换、seed 替换和在线下载均禁止。失败分区不得产生完成 manifest。

### 3.3 Signal Adapter

`backend/quantradar/kronos/signal/adapter.py` 是无 Torch 的纯函数模块。对每只股票的每条有效路径计算：

```text
path_return = predicted_close_day_10 / predicted_open_day_1 - 1
pred_return = median(path_return)
q10/q50/q90_return = corresponding quantile(path_return)
up_probability = mean(path_return > 0)
uncertainty = population_std(path_return)
```

出现非有限值、非正价格或无完整 10 日输出的路径记为 invalid。至少一条有效路径才能生成分数，否则股票保留在 Artifact 中但 `eligible=false`。有效股票按 `pred_return` 降序、`security` 升序稳定排名。

### 3.4 Artifact 与恢复

`backend/quantradar/kronos/signal/store.py`：

- 用 `config + model lock + data contract hash + data commit + requested dates` 生成 `signal_run_id`；
- 每周先写临时目录，校验文件哈希后原子重命名为正式分区；
- `partition_manifest.json` 是分区完成的唯一依据；
- 恢复时重新校验配置指纹、输入哈希、预测哈希和所有文件哈希；
- 将有效分区按日期和证券排序合并为根级 `signals.parquet`；
- 原子更新 `progress.json` 和根 `manifest.json`。

不完整临时目录可安全覆盖。正式分区校验失败时停止并报告损坏，不静默跳过。

### 3.5 Portfolio

`backend/quantradar/kronos/portfolio.py` 接收规范 Signal DataFrame。每个 `execution_date` 选择 `eligible=true` 且 `pred_return` 有限的前 TopK；少于 TopK 时对可用股票等权。输出长表 `target_weights.parquet`，字段为：

```text
strategy_version, signal_date, execution_date, security,
rank, target_weight, reason, signal_run_id, signal_hash
```

权重转换是确定性的，不包含风险阈值、择时或隐式现金比例。

### 3.6 BulletTrade Bridge

通用 Target Weight Bridge 接受宽表权重和 `rebalance_frequency`。它生成 JoinQuant 兼容策略源码，并调用 `run_unified_backtest`：

- 调仓执行时只能选择严格早于当前执行时刻且已生效的最近目标权重；
- Kronos 使用每周调仓，Qlib 继续保持现有月度行为；
- 订单、成交、账户、成本、指标、HTML 和 CSV 全由 BulletTrade 产生；
- 回测目录附带信号 manifest、策略锁和 `target_weights.parquet`。

桥接不得计算收益、Sharpe、最大回撤或其他 BulletTrade 已提供指标。

### 3.7 CLI 编排

新增 `scripts/kronos_research_pipeline.py` 和 Makefile 目标 `kronos-research-pipeline`。CLI 顺序执行数据快照检查、可恢复信号生成、Target Weight 转换和 BulletTrade 回测，最终打印 JSON 摘要及门禁状态。失败返回非零退出码，不输出 PASS 标志。

## 4. 门禁与状态

Goal 2 完成时可设置：

```text
engineering_ready = true
signal_research_ready = true  # 仅当现有覆盖率和每周样本数门槛通过
formal_backtest_ready = false
real_assist_data_ready = false
```

BulletTrade 报告在当前数据条件下必须标记 `research_only=true`。工程成功不等于信号有效；RankIC、分组收益或策略收益为负时仍可工程验收，但研究门禁必须如实失败。

## 5. 错误处理

- 无 PIT 周、少于 50 只合格股票、无下一交易日或无 10 日预测区间：该周记为 blocked，不伪造信号。
- GPU、模型锁或输出校验失败：保留日志，分区不提交。
- Dolt HEAD 在运行中改变：立即终止，禁止合并根级 Artifact。
- Parquet schema、配置指纹或哈希不匹配：恢复失败并指出具体文件。
- 空 Target Weight：禁止启动回测。
- 回测失败：保留 SignalRun，回测状态失败，不删除可复用信号。

## 6. 测试策略

所有生产代码遵循测试先行：

- adapter 单测覆盖收益、分位数、上涨概率、无效路径和稳定排名；
- store 单测覆盖原子提交、恢复跳过、损坏拒绝和配置不一致；
- portfolio 单测覆盖 TopK、并列排序、少量标的和权重和；
- bridge 回归测试覆盖 Qlib 月度默认和 Kronos 周度 T+1；
- subprocess contract 测试不依赖 GPU，验证命令、离线环境和结果校验；
- 集成测试用小型确定性预测夹具跑通 Artifact 到 BulletTrade；
- 最终真实验收使用固定模型和本地 Dolt，至少生成一个真实周分区及一个多周研究回测。

真实 GPU 测试与需要本地 Dolt 的测试必须明确标记；缺少环境只能报告 skip 或 blocked，不能称为通过。

## 7. 完成定义

- 新 PRD、本设计、实现计划与代码均提交在隔离分支；
- 新增测试和受影响的现有测试通过；
- 至少一个真实 GPU 周分区可复现；
- CLI 产出规范 Signal、Target Weight 和 BulletTrade 原生报告；
- Artifact 哈希链可从回测追溯到预测、输入、数据 commit 与模型 revision；
- 文档明确当前仍是研究用途，两个正式门禁保持关闭。
