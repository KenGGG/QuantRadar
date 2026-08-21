# QuantRadar Kronos 投资研究工作台 PRD v1

状态：已批准，进入 Goal 2 实施  
日期：2026-08-21

## 1. 产品目标

在 QuantRadar 内建立可复现的 Kronos 投资研究闭环：

```text
investment_data
  -> Kronos-base
  -> Signal Artifact
  -> Target Weight
  -> BulletTrade
  -> Research Report
```

系统用于验证 Kronos 预测是否能形成有统计意义的 A 股排序信号，并逐步发展为个人 AI 量化研究工作台。它不是 Kronos 论文复现项目，也不新建交易或回测引擎。

## 2. 已有基础与不变约束

- Goal 0 已确认价格输入契约，但公司行为、ST、停牌和最新沪深 300 PIT 成分仍不完整。
- Goal 1 已取得 `KRONOS_BASE_GPU_RUNTIME_PASS`，固定 Kronos-base、Tokenizer、源码提交和 CUDA 环境。
- `investment_data` 是首要事实源，以一次运行开始时的 Dolt commit 固定数据快照。
- Kronos 推理只在独立 `.venv-kronos` 子进程运行；QuantRadar 主环境不得导入 Torch。
- 组合回测必须复用 BulletTrade 的撮合、账户、订单、成本、指标和报告能力。
- 数据缺口未解决前，`formal_backtest_ready=false`、`real_assist_data_ready=false`；研究结果不得表述为正式回测或实盘建议。
- 将来接入补充数据时，必须先通过 ETL 落入本地补充表，再由 Provider 读取；运行时不得临时调用外部行情接口。

## 3. Goal 顺序

### Goal 1：Kronos Runtime（已完成）

完成标志：`KRONOS_BASE_GPU_RUNTIME_PASS`。

### Goal 2：Kronos Investment Research Pipeline（当前）

交付以下可通过 CLI 验证的闭环：

1. Kronos Signal Adapter；
2. Prediction 到 Signal 的确定性转换；
3. 可增量、可恢复、可校验的 Signal Artifact；
4. 周度 TopK 等权 Target Weight；
5. Target Weight 到 BulletTrade 的桥接；
6. BulletTrade 原生回测报告与研究门禁；
7. 一条端到端 CLI 命令。

Goal 2 禁止实现 WebUI、参数矩阵、模型微调、实盘交易和补充数据源。

### Goal 3：Kronos WebUI Experiment Workspace

在 Goal 2 接口稳定后提供参数配置、实验保存、运行状态和结果比较。WebUI 只调用后端 API，不直接加载模型或调用 BulletTrade 内部对象。

### Goal 4：Kronos Parameter Research

对 lookback、prediction horizon、采样数、TopK 和调仓周期执行预登记实验矩阵，输出可复现排名。模型 Fine-tuning 不属于本阶段。

### Goal 5：Kronos Data Completeness

以 `investment_data` 优先、补充表兜底的方式完善 ST、停牌、股票列表、公司行为和 PIT 指数成分。补充源数据必须带来源、抓取时间、有效日期和内容哈希。

## 4. Goal 2 用户流程

用户运行 CLI，指定信号日期范围、TopK、初始资金和输出目录。系统按周执行：

1. 读取该周 PIT 股票池和截至信号日可见的 90 个交易日输入；
2. 在独立 GPU 子进程用固定五条采样路径预测未来 10 个交易日；
3. 将路径预测转换成个股收益分布、上涨概率、不确定性和横截面排名；
4. 原子写入该周分区并更新 SignalRun 进度；
5. 将每周排名前 TopK 的股票转换成下一交易日生效的等权目标仓位；
6. 用 BulletTrade 统一回测链生成原生指标和 HTML 报告；
7. 生成 manifest、哈希和真实研究门禁状态。

中断后重跑时，只有通过哈希校验的已完成周可跳过；损坏或配置不一致的分区必须重新计算。

## 5. Signal Artifact

根目录：

```text
artifacts/kronos/signals/<signal_run_id>/
├── manifest.json
├── config.json
├── model_lock.json
├── data_contract.json
├── signals.parquet
├── target_weights.parquet
├── progress.json
├── weeks/<signal_date>/
│   ├── input_manifest.json
│   ├── predictions.npz
│   ├── signals.parquet
│   └── partition_manifest.json
└── runner.log
```

`signals.parquet` 的规范字段：

```text
signal_run_id
signal_date
execution_date
security
prediction_horizon
pred_return
q10_return
q50_return
q90_return
up_probability
uncertainty
rank
eligible
eligibility_status
exclusion_reason
input_start_date
input_end_date
input_rows
input_hash
valid_path_count
invalid_path_count
model_version
model_revision
tokenizer_revision
data_commit
prediction_hash
```

其中 `pred_return` 等于路径收益中位数，`uncertainty` 等于路径收益标准差，`rank=1` 表示当周预测收益最高。收益均由预测窗口首个开盘价到最后一个收盘价计算。

## 6. 第一版策略

第一版只实现 `kronos_topk_equal_weight_v1`：

- 周度信号；
- 按 `pred_return` 降序选择 TopK，默认 20；
- 等权；
- 信号在 `execution_date` 执行，必须严格晚于 `signal_date`；
- 未入选的原持仓目标权重为零；
- 不实现风险过滤和市场择时，避免在信号有效性得到证明前增加自由度。

## 7. 验收

Goal 2 工程验收必须同时满足：

- 相同输入、模型锁、配置和 seed 生成相同预测及 SignalRun 哈希；
- 单周和多周信号均可生成，增量恢复测试通过；
- 每个执行日只使用更早信号，T+1 防未来测试通过；
- 目标权重每周非空行之和等于 1；
- 端到端 CLI 能生成 Signal Artifact、Target Weight 和 BulletTrade 原生报告；
- 运行开始与结束的 Dolt commit 相同；
- 数据缺口如实保留研究限定，不提升正式回测或实盘门禁。

