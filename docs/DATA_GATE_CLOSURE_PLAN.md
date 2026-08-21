# Kronos 数据门禁收敛方案（Goal 5A-refactor）

> 本文件取代首轮「补齐所有数据关旧门禁」的理解。
> 关键结论（经复核 Kronos 官方要求与代码）：**当前 `investment_data` 持续更新的核心行情数据，
> 已经足以支撑 QuantRadar 进入 Kronos 实质性信号研究阶段。现在首先应修正的是 QuantRadar 的
> 「数据门禁定义」，而不是继续为了 Kronos 去补一大堆它根本不需要的数据。**

基线：`main@be495bb`（Goal 0/1/2 已冻结并合并）。本变更在分支 `feat/kronos-gate-refactor`
（worktree `.worktrees/kronos-gate-refactor`）。

---

## 0. 一句话结论

- Kronos `predict()` **只依赖** `open/high/low/close` + `x_timestamp`/`y_timestamp`；
  `volume`/`amount` 可选（0 填即可）。它**不需要** 000300 PIT、ST 标记、停牌、涨跌停、
  证券主数据、公司行为事实表。
- 旧代码把「高保真回测 / 实盘辅助」所需的数据，错误地提升为「Kronos 必须通过的全局门禁」，
  并用 `raise RuntimeError("No exact 000300.SH PIT snapshot ...")` 把 Kronos 硬绑死到 000300 PIT。
- 修正方式：**能力可用 ≠ 数据完美**。门禁改为 4 层能力模型 + 独立的 `csi300_pit_ready`；
  默认研究宇宙改为 `all_a_liquid`（仅由持续更新的 `final_a_stock_eod_price` 构造，PIT-free）。
  单一能力（如 000300 PIT）缺失，**不再阻塞** Kronos 信号研究。

---

## 1. 旧模型的问题（已逐条核对代码）

| 位置 | 旧行为 | 问题 |
|------|--------|------|
| `data_audit/gates.py:88` | `signal_ready = price_ready and pit_ready` | 把「Kronos 研究」与「严格 CSI300 历史研究」混为一谈；`pit_ready` 要求 000300.SH 从 2015→最新，阻塞一切 |
| `data_audit/gates.py:64` | `required_start = first.replace(year=2015, month=1, day=1)` | 硬编码 2015 起点——这是 QuantRadar 自定义的 CSI300 研究要求，不是 Kronos 要求 |
| `signal/inputs.py:67` | `raise RuntimeError("No exact 000300.SH PIT snapshot for {day}")` | 代码层把 Kronos 绑死到 000300 PIT；无快照即崩溃，即便 Kronos 根本不需要 |
| `runtime/inputs.py:241` | `raise RuntimeError("No real 000300.SH PIT snapshot is available")` | 同上（实时包路径） |
| `signal/inputs.py:28` `list_signal_dates` | 直接查 `ts_index_weight WHERE index_code='000300.SH'` | 000300 无快照 → 无信号日 → 无研究 |
| `select_eligible_windows` (`runtime/inputs.py:71`) | 120日/90日/ST/停牌/流动性过滤 | **已对 bao 状态缺失优雅降级**（status=None→保留并标记 `partial_status_symbols`），不依赖外部数据，非阻塞 |

旧门禁结果（实测）：仅 `price_semantics_ready=true`，其余 `signal_research_ready` /
`formal_backtest_ready` / `real_assist_data_ready` 全 false——把 Kronos 研究也一起关了，
与「Kronos 只需 OHLC」的事实矛盾。

---

## 2. 新门禁模型（4 层能力 + 独立 CSI300 PIT）

底层 4 项证据不变：`price_semantics` / `corporate_action` / `pit_universe` / `latest_tradeability`。
复合门禁重写为：

```text
price_data_ready            = price_semantics.ready                         # True
kronos_input_ready          = price_data_ready                              # OHLC(+VA) 满足 Kronos
kronos_signal_research_ready= kronos_input_ready and universe_default_ready # True（all_a_liquid 仅依赖价格）
csi300_pit_ready            = pit_universe.ready                            # 独立能力（PARTIAL: 2020-2022）
realistic_backtest_ready    = kronos_signal_research_ready
                           and latest_tradeability.status != BLOCKED        # True；fidelity=PARTIAL
real_assist_data_ready      = kronos_signal_research_ready
                           and latest_tradeability.status == PASS           # False（当前 stale）
```

- `universe_default_ready` 恒为 True：`all_a_liquid` 仅依赖持续更新的价格即可构造，不依赖任何 PIT 成分快照。
- 输出额外带 `fidelity` 字典（PASS / PARTIAL / BLOCKED 文案）与旧键别名 `signal_research_ready`=
  `kronos_signal_research_ready`、`formal_backtest_ready`=`realistic_backtest_ready`（便于平滑过渡）。
- 保留 `derive_pit_universe_evidence` / `derive_latest_tradeability_evidence` 仅用于 `csi300_pit_ready`
  与 `fidelity` 计算。

### 实测（make kronos-data-audit，Dolt rlr4k90…）

```json
{
  "kronos_signal_research_ready": true,
  "realistic_backtest_ready": true,
  "real_assist_data_ready": false,
  "csi300_pit_ready": false,
  "fidelity": {
    "kronos_input_ready": "PASS",
    "kronos_signal_research_ready": "PASS",
    "csi300_pit_ready": "PARTIAL",
    "realistic_backtest_ready": "PARTIAL",
    "real_assist_data_ready": "BLOCKED"
  }
}
```

含义：
- **Kronos 信号研究已解绑**：默认宇宙 `all_a_liquid`，只用持续更新的 `final_a_stock_eod_price`。
- **realistic backtest 可用但保真度有限**（tradeability 覆盖滞后至 2023-06）。
- **real assist / 实盘辅助仍 BLOCKED**（tradeability 未达 PASS）——符合预期，需 Goal 5B 补齐。
- **000300 PIT 是独立能力**（PARTIAL），其缺失不再阻塞 Kronos 研究；它是「严格 CSI300 历史研究 /
  实盘辅助」所需的独立能力，可单独推进。

---

## 3. 宇宙可配置（universe_spec）

新增 `backend/quantradar/kronos/universe_spec.py`：

```python
class Universe(str, Enum):
    ALL_A_LIQUID = "all_a_liquid"   # 默认
    CSI300_PIT    = "csi300_pit"
    CSI500_PIT    = "csi500_pit"
    CSI1000_PIT   = "csi1000_pit"

INDEX_CODE  = {CSI300_PIT:"000300.SH", CSI500_PIT:"000905.SH", CSI1000_PIT:"000852.SH"}
JQ_INDEX_CODE = {CSI300_PIT:"000300.XSHG", CSI500_PIT:"000905.XSHG", CSI1000_PIT:"000852.XSHG"}
DEFAULT_UNIVERSE = ALL_A_LIQUID
```

- `all_a_liquid`：由 `final_a_stock_eod_price` 直接枚举（沪/深 A 股，已排除北交所 BJ* 与指数代码
  `SH000xxx`/`SZ399xxx`）。上市/存续由价格历史本身推导（PIT 正确，无需证券主数据）。
- `csi*_pit`：沿用旧行为，基于对应指数 `ts_index_weight` PIT 快照；无快照仍 `raise`（对该宇宙正确）。

`list_signal_dates` / `collect_week_input_package` / `collect_real_input_package` 均增加
`universe` 形参并委托/分支；`publish_input_package` 在 manifest 写入 `universe` 字段。

CLI：`scripts/kronos_research_pipeline.py --universe {all_a_liquid|csi300_pit|csi500_pit|csi1000_pit}`
（默认 `all_a_liquid`）。

---

## 4. 代码改动清单（本 PR）

| 文件 | 改动 |
|------|------|
| `kronos/universe_spec.py` | **新增**：`Universe` 枚举、`list_signal_dates`、`all_a_liquid_symbols`、`listed_trade_days`、`latest_price_date`、`parse_universe` |
| `kronos/data_audit/gates.py` | 重写为 4 层能力门禁 + 独立 `csi300_pit_ready` + `fidelity` + 旧键别名 |
| `kronos/signal/inputs.py` | `list_signal_dates` 委托 universe_spec；`collect_week_input_package` 增加 `universe`，`all_a_liquid` 分支不再查 PIT、不再 `raise` |
| `kronos/runtime/inputs.py` | `collect_real_input_package` 增加 `all_a_liquid` 分支（去掉 `raise`）；`publish_input_package` 增加 `universe` 字段 |
| `kronos/pipeline.py` | `run_research_pipeline` 增加 `universe` 形参透传；`research_manifest`/`gate` 写入真实计算新键（不硬编码 false） |
| `scripts/kronos_data_audit.py` | 摘要打印新门禁键 |
| `scripts/kronos_research_pipeline.py` | 新增 `--universe` 参数 |
| 测试 | 更新 `test_data_audit_core/runner/cli`、`test_pipeline`、`test_pipeline_cli`、`test_signal_inputs`、`test_runtime_inputs(_live)`；**新增** `test_universe_all_a_liquid.py` |

**不在范围（明确不做）**：不补数据（BaoStock/Tushare 入库）→ Goal 5B；不接新数据源；不改
`FEATURE_NAMES`；不做 Goal 3/4；不写生产级回测/实盘辅助。

---

## 5. Goal 5B（数据补齐，降级为非阻塞、仅提升保真度）

数据补齐**不再是 Kronos 研究的阻塞项**。它被降级为「提升 realistic / live 层级保真度」的可选工作：

| 能力 | 当前 | Goal 5B 目标 | 是否阻塞 Kronos 研究 |
|------|------|--------------|----------------------|
| 价格语义 | PASS（→2026-08-18） | 维持 | 否 |
| 公司行为（分红/拆股） | PARTIAL（无独立事实表） | 建独立事件表 | 否 |
| 沪深300 PIT 成分 | PARTIAL（2020-2022） | 补齐至最新（用户侧 Tushare token / CSIndex 文件） | 否（独立能力） |
| ST / 停牌 | PARTIAL（→2023-06-09） | 补齐 | 否 |
| 涨跌停 | PARTIAL（→2023-06-12） | 补齐 | 否 |
| 股票主数据 | PARTIAL（→2022-07-18） | 补齐（PIT 由价格历史近似已可） | 否 |
| 实时可交易状态（live assist） | BLOCKED（tradeability 未 PASS） | 补齐后 `real_assist_data_ready=true` | 仅阻塞实盘辅助 |

> 原则：外部数据 → 本地加载/版本化 → 审计 → Provider → QuantRadar；回测中禁止实时抓取；
> 禁止 mock / 合成 / 前向填充；需用户侧凭证的部分（Tushare token、CSIndex 文件）单列
> `USER_ACTION_REQUIRED`。

---

## 6. 验收

1. `make kronos-data-audit` → `kronos_signal_research_ready=True`，`realistic_backtest_ready=True`
   （fidelity PARTIAL），`real_assist_data_ready=False`，`csi300_pit_ready` 反映 PARTIAL。
2. 对近期日期（如 2026-08 某周）成功构建 `all_a_liquid` 输入包（CPU+DB，无需 GPU），**无 RuntimeError**，
   eligible 符号数千级 → 证明 Kronos 研究已在当前数据上解绑。
3. kronos 单测全绿；CI 无回归。
4. 主干 `main` 工作树保持干净（改动在 `feat/kronos-gate-refactor` worktree + 分支，PR 合并后才入 main）。

---

## 7. 后续顺序建议（非阻塞）

1. **立即可做**：Kronos 信号研究（RankIC、分组收益、信号排序、TopK 权重），默认 `all_a_liquid`。
2. **Goal 5B（用户侧凭证）**：补齐 000300 PIT / ST / 停牌 / 涨跌停 / 主数据 → 提升 realistic 保真度、
   解锁 `real_assist_data_ready`。
3. **Goal 3 / 4**：WebUI 工作区、参数研究（仅在用户决策后推进，且不受本门禁阻塞）。
```

（预期研究水平：当前 `all_a_liquid` 即可支撑「Kronos 信号有效性」的初步实证；严格的「CSI300 历史
可比基准」需等 Goal 5B 补齐 000300 PIT 后另立独立能力，不影响本阶段信号研究。）
