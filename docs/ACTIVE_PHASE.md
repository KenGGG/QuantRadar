# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Phase -1 + Phase 0**

本轮只允许完成：

```text
基础环境建立
+
现状审计
```

禁止进入 Provider、回测、FastAPI、WebUI 或 Qlib 功能开发。

---

# 一、目标

在：

```text
/data/Projects/a-stock-research/QuantRadar
```

建立可信的 QuantRadar 开发基线，并准确确认当前 Ubuntu、BulletTrade、investment_data 和 Qlib 的真实状态。

---

# 二、如果 QuantRadar 目录为空（或需要重建基线）

将 BulletTrade 以 vendored 快照方式放入 `vendor/bullet-trade/`，QuantRadar 根目录为其自有 Git 仓库：

```bash
cd /data/Projects/a-stock-research/QuantRadar

git clone https://github.com/BulletTrade/bullet-trade.git vendor/bullet-trade

rm -rf vendor/bullet-trade/.git        # 禁止嵌套 Git 仓库
```

说明：

```text
QuantRadar 根目录是项目自己的仓库（.git 在根）
vendor/bullet-trade 只是代码基线快照，不保留完整 Git 历史
upstream 信息（URL + base commit）记录在 docs/BASELINE.md，不在此建立 remote
禁止创建 vendor/bullet-trade 以外的嵌套仓库
禁止向 upstream 推送（见 02 第二节）
安装基线：pip install -e ./vendor/bullet-trade
```

最终目录形态（与 docs 控制文档一致）：

```text
QuantRadar/
├── .git/
├── .venv/
├── vendor/bullet-trade/      # BulletTrade 基线（无 .git）
├── backend/
├── frontend/
├── docs/
├── tests/
├── strategies/
├── pyproject.toml
├── requirements.lock
└── .gitignore
```

---

# 三、建立项目 Python 环境

目标：

```text
Python 3.11
```

在：

```text
QuantRadar/.venv
```

建立环境。

安装当前项目：

```bash
pip install -e .
```

禁止安装另一份 PyPI BulletTrade 与源码版并存。

确认：

```python
import bullet_trade
print(bullet_trade.__file__)
```

必须指向 QuantRadar 当前源码。

---

# 四、验证 BulletTrade Ubuntu 能力

至少验证：

```text
bullet-trade --version
bullet-trade lab --diagnose
BacktestEngine import
```

调查：

```text
哪些能力跨平台
哪些能力依赖Windows/QMT
```

记录事实。

当前阶段不得安装 QMT。

---

# 五、审计 investment_data

数据库位置：

```text
/data/investment_data
```

默认只读。

禁止：

```text
INSERT
UPDATE
DELETE
ALTER
DOLT PULL
DOLT COMMIT
```

调查：

```text
Dolt commit
branch
schema
全部相关table
min/max date
row count
symbol count
```

重点确认真实存在与否：

```text
A股日线
交易日历
指数成分
指数权重
涨跌停
停牌
ST
公司行为
ETF
```

不得根据 README 猜测。

必须以真实数据库查询为准。

---

# 六、验证 Qlib

在同一个：

```text
QuantRadar/.venv
```

安装：

```text
pyqlib
```

验证 import。

搜索机器上是否已经存在：

```text
Qlib Bin
cn_data
qlib_data
```

如存在：

记录：

```text
路径
calendar
instrument
latest date
```

如不存在：

标记：

```text
QLIB_DATA_NOT_BUILT
```

本轮不要立即开发新的数据转换器。

---

# 七、审计 BulletTrade Provider机制

读取真实源码，回答：

```text
1. DataProvider ABC当前接口是什么？
2. Provider如何创建？
3. 是否已有外部Provider注册机制？
4. set_data_provider如何工作？
5. get_price/history等外层如何调用Provider？
6. BacktestEngine如何取得Provider？
7. 防未来数据机制在哪里？
```

此阶段：

```text
只调查
不修改
```

---

# 八、输出文件

必须创建或更新：

```text
docs/BASELINE.md
docs/CURRENT_STATE.md
```

`BASELINE.md` 记录：

```text
OS
Python
Node
BulletTrade version
BulletTrade base commit
Git remotes
investment_data path
Dolt commit
latest trade date
Qlib version
Qlib data path
```

`CURRENT_STATE.md` 记录：

```text
已验证事实
现有能力
缺失能力
Provider扩展现状
数据表映射
风险
下一阶段建议
```

---

# 九、禁止事项

本轮禁止开发：

```text
InvestmentDataProvider
FastAPI
PostgreSQL schema
Worker
React
WebUI
Qlib Model
ETF补数
QMT
实盘
```

禁止因为发现数据缺失就提前修。

首先只记录真实状态。

---

# 十、验收

完成后必须明确输出：

```text
[PASS/FAIL] QuantRadar Git基线
[PASS/FAIL] 项目内Python .venv
[PASS/FAIL] BulletTrade Ubuntu Core
[PASS/FAIL] investment_data可访问
[PASS/FAIL] A股日线可查询
[PASS/FAIL] 交易日历可查询
[PASS/FAIL] Qlib import
[PASS/PARTIAL] Qlib数据
[PASS] Provider机制完成源码审计
```

只有上述工作完成，才标记：

```text
BOOTSTRAP_AND_AUDIT_PASS
```

---

# 十一、结束条件

完成：

```text
BASELINE.md
CURRENT_STATE.md
测试证据
Git commit
```

后立即停止。

不要自动开始 Phase 1。

最终报告：

```text
## 已完成
## 环境事实
## investment_data事实
## BulletTrade事实
## Qlib事实
## Blocked
## 风险
## 下一阶段建议
```
