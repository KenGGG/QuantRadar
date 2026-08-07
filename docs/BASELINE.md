# 环境事实（BASELINE）

文件：`docs/BASELINE.md`

> 本文件记录**不可变的环境事实**，由 ACTIVE_PHASE（Phase -1/0）审计任务首次填写。
> 仅在环境真实变化（升级 Python、换 commit、重建 Qlib 数据等）时更新。
> 用于排查环境 / 依赖问题时快速核对真实数值。

---

# 环境事实

```text
OS:                  Linux (Ubuntu)；平台架构 x86_64
Python:              3.12.3   （支持范围 >=3.11,<3.13；本机仅 3.12.3 可用，已验证）
Node:                v22.23.1
BulletTrade version: 0.9.2（tag v0.9.2）
BulletTrade base commit: be0451be09b1de3516d3959e70008031824103cb
Git remotes:         origin = https://github.com/KenGGG/QuantRadar.git（QuantRadar 自有仓库）
                      vendor/bullet-trade 不配置 remote（upstream URL 仅记于此；base commit = be0451b）
investment_data path:/data/investment_data
investment_data 类型:  Dolt 数据库（.dolt / .doltcfg），SQL server 监听 127.0.0.1:3307
Dolt commit:         vg0ic1rpm6ilssoljq3ruv8pavr1blb1（committer: bruce_h_z_sun）
latest data date:    2026-08-04（final_a_stock_eod_price 最大 tradedate）
Qlib version:        pyqlib 0.9.7（已装入 .venv）
Qlib data path:      QLIB_DATA_NOT_BUILT（全机未找到 qlib_data / cn_data / .qlib）
```

---

# 数据库访问方式

```text
investment_data 经 Dolt SQL server 提供，端口 3307
只读访问命令示例（禁止写操作）：
  python -c "import pymysql; c=pymysql.connect(host='127.0.0.1',port=3307,user='root',database='investment_data'); ..."
dolt CLI 可用：/usr/local/bin/dolt（版本 1.86.0；注意比官方新版本旧）
禁止：INSERT / UPDATE / DELETE / ALTER / DOLT PULL / DOLT COMMIT
```

---

# Python 环境

```text
虚拟环境：/data/Projects/a-stock-research/QuantRadar/.venv（项目内，已 gitignore）
安装方式：pip install -e ./vendor/bullet-trade（bullet-trade 0.9.2 可编辑，指向 vendored 当前源码）
验证：import bullet_trade → /data/Projects/a-stock-research/QuantRadar/vendor/bullet-trade/bullet_trade/__init__.py
附加安装：pyqlib 0.9.7（Phase 10 前仅验证 import）
```

---

# 验收结论（ACTIVE_PHASE §十）

```text
[PASS] QuantRadar Git 基线（根目录自有仓库 origin=KenGGG/QuantRadar；vendor/bullet-trade 为受控快照无 remote）
[PASS] 项目内 Python .venv（python3.12.3；目标 3.11 缺失，见风险）
[PASS] BulletTrade Ubuntu Core（bullet-trade --version=0.9.2；BacktestEngine import OK；lab --diagnose OK）
[PASS] investment_data 可访问（Dolt 3307 SELECT 正常）
[PASS] A 股日线可查询（final_a_stock_eod_price）
[PASS] 交易日历可查询（ts_trade_day_calendar）
[PASS] Qlib import（pyqlib 0.9.7）
[PARTIAL] Qlib 数据（import OK；QLIB_DATA_NOT_BUILT）
[PASS] Provider 机制完成源码审计（见 CURRENT_STATE 第七节的 7 问回答）
→ BOOTSTRAP_AND_AUDIT_PASS 达成
```
