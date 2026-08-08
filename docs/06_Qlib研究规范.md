# Qlib 研究规范

文件：`docs/06_Qlib研究规范.md`

本文件仅在进入 **Qlib 阶段（Phase 9 / Phase 10）** 时才需要读取。

Qlib 是 QuantRadar 使用的研究依赖，不是回测核心（见 00 / 01）。

---

# 一、Qlib 不是回测核心

```text
回测核心 = BulletTrade（见 04）
Qlib 角色 = 高级因子研究 / 模型训练 / 预测
禁止：用 Qlib 替换 BulletTrade 撮合与组合会计
禁止：重新开发 Qlib 核心
```

---

# 二、Qlib 使用已有的 investment_data 导出

```text
Qlib 数据来自 investment_data 的受控导出，不另起数据生产
导出格式见第三节 signal parquet contract
禁止：Qlib 直接绕过 Provider 访问未审计数据源
```

---

# 三、研究范围（Phase 10，部分已在严谨研究型 V1 落地）

已实现（严谨研究型 V1 T1–T4）：

```text
Alpha158        —— 因子集（QLIB_BULLETTRADE_LOOP_PASS）
LightGBM        —— 模型（run_qlib_loop）
多模型探测       —— available_models / _get_model_class（lgb 可用，xgb/mlp 缺依赖抛 NotImplementedError，不伪造）
参数寻优         —— grid_search_qlib（固定 seed，按 IC 选优，可复现）
walk-forward    —— walk_forward_qlib（逐折不重叠防泄漏，可复现）
样本外验证       —— run_research_oos（grid+OOS 结构化可复现报告，JSON+MD）
Target Weight   —— topk_target_weights（等权 Top-K）
```

训练切分：

```text
Train / Valid / Test 严格按时间切分（防未来函数，见 03 第六节）
walk-forward 各折 segments 不重叠（assert_segments_disjoint 守卫）
```

评估指标：

```text
IC
RankIC
```

---

# 四、signal parquet contract（信号落盘契约）

Qlib 产出的预测/信号以 Parquet 落盘，供 BulletTrade 闭环使用：

```text
字段约定（建议，待 Phase 10 落地确认）：
symbol       证券代码（与 Provider symbol mapping 一致，见 03）
date         信号日期（PIT 有效）
score        模型预测分
target_weight 目标权重（可选）
```

```text
文件：runs/<run_id>/snapshot/signal/<model>/signal.parquet
该 Parquet 是 Qlib → BulletTrade 的契约接口
```

---

# 五、Snapshot alignment（对齐）

```text
Qlib 信号必须能与 BulletTrade Snapshot（见 04）对齐：
相同 symbol mapping
相同交易日历（见 03 get_trade_days）
相同 PIT 约束
```

```text
禁止：Qlib 信号日期与 BulletTrade 回测日期错位导致未来函数
```

---

# 六、Qlib → BulletTrade 闭环

```text
investment_data
→ Provider（03）
→ Qlib 训练/预测（signal parquet）
→ BulletTrade 以信号/目标权重构建组合并回测（04）
→ Snapshot 保存可复现实验
```

闭环验收：

```text
用 Qlib 输出的 target_weight 跑 BulletTrade 回测
Result Hash 可复现（见 04 第五节）
```

---

# 六之一、已验证的数据构建约定（对齐官方 investment_data）

`backend/quantradar/qml/dump.py` 的 qlib 日线数据构建已与官方
[chenditc/investment_data](https://github.com/chenditc/investment_data) 导出方式交叉核对，
确保字段与复权口径一致（审计可复现）：

```text
字段集（_QLIB_FIELDS）：
  open / high / low / close / volume / amount / vwap

VWAP 口径（与官方一致）：
  vwap = amount * 10 / volume
  官方 SQL：select *, amount / volume * 10 as vwap from final_a_stock_eod_price

日历：SSE，is_open=1，自 2000-01-04
复权：使用 Provider 提供的后复权 close（已审计，禁止自造复权）
```

Point-in-Time 选股（`select_universe`）：

```text
按 ts_a_stock_list 过滤：
  list_date <= start AND (delist_date IS NULL OR delist_date >= start)
按 ts_code 排序取前 N，禁止纳入回测区间开始前已退市标的
```

mlflow 落盘（防仓库污染）：

```text
qlib 默认 exp_manager.uri = file:<cwd>/mlruns，且忽略 MLFLOW_TRACKING_URI
修复：qlib.init 显式传入 exp_manager，uri 指向 tempfile.mkdtemp 临时目录
兜底：.gitignore 已忽略 mlruns/
```

---

# 八、严谨研究型 V1 研究正确性规则（已落地 T1–T4）

以下规则是 QuantRadar「严谨研究型 V1」已强制落地的工程与研究正确性底线，
任何新研究代码都必须遵守。

## 8.1 不伪造（最高原则）

```text
模型不可用（依赖缺失）必须显式报错，绝不静默回退或编造结果：
  - available_models() 按真实 import 探测 lgb/xgb/mlp
  - 本环境仅 LGBModel 可用（xgb 缺 xgboost、mlp 缺 torch）
  - _get_model_class 对未知模型抛 ValueError；对已知但缺失依赖抛 NotImplementedError
  - run_research_oos / grid_search / walk_forward 任何失败都如实抛出，绝不补零/造指标
```

## 8.2 多模型 + 参数寻优

```text
grid_search_qlib：
  - 固定随机种子（默认 42）注入 lgb/xgb，保证可复现（同输入同输出）
  - 遍历超参组合，按 IC 选优（best_params / best_ic）
  - 仅对有限 IC 的组合参与选优；全为 NaN 时 best=None（如实反映）
```

## 8.3 walk-forward 防泄漏（样本外稳健性）

```text
walk_forward_qlib：
  - 滚动窗口逐折 Train/Valid/Test，每折 segments 严格不重叠
  - assert_segments_disjoint 守卫：任一层重叠即拒绝（防未来数据泄漏）
  - 固定 seed 可复现；输出各折样本外 IC 作为真实 OOS 表现
  - 杜绝单一切分的乐观偏差
```

## 8.4 可复现报告（OOS）

```text
run_research_oos：
  - 端到端（grid 选优 + walk-forward 多折 OOS）
  - 结构化报告（JSON 可序列化）：config / grid / folds / oos(均值·标准差·正IC占比) / environment(git commit+版本)
  - 固定 seed + 记录完整配置与环境 → 同输入逐字节一致 JSON
  - scripts/research_oos.py：复用或自动构建 qlib_data，产出 <out>.json + <out>.md
```

## 8.5 Qlib 进程初始化隔离（踩坑结论）

```text
- qlib 不允许进程内重复 init（RecorderInitializationError）；初始化状态以 C.registered 为准
- _ensure_qlib_init 是 qlib 初始化的**唯一入口**：build_qlib_data 与 run_qlib_loop 都经它，
  杜绝任一处直接 qlib.init 导致重复 init 把全局 C 配置重置/锁定（引发 loky 子进程崩溃）
- 跨目录请求仅重定向 C['provider_uri']={"day": new_dir}，不重 init
- joblib_backend 强制 'threading' 必须在每次 init/重定向后立即设置：
  重定向 provider_uri 会把它重置回默认 'multiprocessing'，否则 inst_calculator
  在 loky 子进程里因缺已注册的 C 崩溃（AttributeError: No such 'registered'）
- lgb 强制 num_threads=1：固定 seed 下训练逐位可复现（OpenMP 多线程在负载下可能非确定）
- 测试共享同一 qlib 目录（与真实「单目录/会话」用法一致），彻底规避跨函数重定向
```

## 8.6 复权口径同源（T1 实测纠正）

```text
final_a_stock_eod_price.close/open/high/low 本身已是连续复权价（除权缺口已消除）
回测腿（读 final.close）与 Qlib 训练（读 final.adjclose 后复权）同源连续复权，
无除权假跳变；fq 已配置化（none/pre/qfq/post/hfq）+ 审计 config 记录 + _FQ_LOCK 线程安全切换
```

## 8.7 测试隔离纪律（CI 安全）

```text
所有依赖 investment_data(Dolt) 的研究测试必须带 @pytest.mark.requires_dolt：
  - conftest autouse _skip_without_dolt 在 Dolt 不可达时自动 skip
  - QUANTRADAR_FORCE_NO_DOLT=1 可模拟无 Dolt 的 CI 环境，确保套件整体绿（跳过而非崩溃）
  - 研究测试共享 qlib 目录（tests/unit/_qml_helpers.build_shared_qlib_dir）避免跨进程重定向
```

---

# 七、与其他文档关系

```text
03 数据：Provider 是 Qlib 数据的上游事实源
04 回测：Qlib 信号最终回到 BulletTrade 闭环
02 架构：Qlib 依赖 pyqlib，仅验证 import 于 Phase -1/0
```
