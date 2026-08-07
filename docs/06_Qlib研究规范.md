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

# 三、研究范围（Phase 10）

只实现：

```text
Alpha158        —— 因子集
LightGBM        —— 模型
Prediction      —— 预测值
Target Weight   —— 目标权重
```

训练切分：

```text
Train / Valid / Test 严格按时间切分（防未来函数，见 03 第六节）
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

# 七、与其他文档关系

```text
03 数据：Provider 是 Qlib 数据的上游事实源
04 回测：Qlib 信号最终回到 BulletTrade 闭环
02 架构：Qlib 依赖 pyqlib，仅验证 import 于 Phase -1/0
```
