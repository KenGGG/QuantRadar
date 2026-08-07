# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Phase 1 — 控制文档校准 + Provider Registry（已完成 / 等待下一阶段授权）**

阶段标志：`CUSTOM_PROVIDER_REGISTRATION_PASS`

```text
本阶段已完成：
  1. 控制文档校准（vendor/bullet-trade 受控快照架构、Git remote、Python >=3.11,<3.13、Provider 状态三分法）
  2. 实现 Generic Provider Registry（register_data_provider / unregister_data_provider）
  3. 单元测试 9/9 通过 + 相关回归通过 + 全量套件中 2 个与 Phase 1 无关的预存收集错误已识别
禁止自动进入 Phase 2。下一阶段需显式授权。
```

---

# 一、目标

在不开发任何具体业务 Provider（`InvestmentDataProvider` 留给 Phase 2）的前提下：

```text
A. 校准控制文档，使其与真实目录架构（vendor/bullet-trade 受控快照）一致
B. 在 BulletTrade 的 _create_provider 之上，增加「通用 Provider 注册表」
C. 让任意外部 Provider 可通过名称注册 / 注销，并经统一入口创建，而无需硬编码新分支
D. 不破坏内置 Provider 的创建路径与认证逻辑
```

---

# 二、范围与边界（强制）

```text
允许：
  - 修改 vendor/bullet-trade/bullet_trade/data/api.py（增加注册表 + 在 _create_provider 插入查表）
  - 修改 vendor/bullet-trade/bullet_trade/data/__init__.py（导出新函数）
  - 新增 vendor/bullet-trade/tests/unit/test_provider_registry.py
  - 更新 docs/ 控制文档（ACTIVE_PHASE / CURRENT_STATE / BASELINE / 02）

禁止：
  - 在 _create_provider 中硬编码 if target == "investment_data"
  - 实现 InvestmentDataProvider（Phase 2 工作）
  - 修改内置 Provider 的创建 / 认证逻辑（jqdata/tushare/miniqmt/remote_qmt/rqdata/easy_tdx）
  - 静默覆盖内置 Provider
  - 自动进入 Phase 2
```

---

# 三、文档校准要求

更新以下文档，统一到真实架构：

```text
架构事实（唯一真源）：
  - QuantRadar 根目录 = 自有 Git 仓库（origin = KenGGG/QuantRadar）
  - vendor/bullet-trade = BulletTrade v0.9.2 受控快照（base commit be0451b），无 .git、无 remote
  - 安装：pip install -e ./vendor/bullet-trade
  - Python 支持范围：>=3.11,<3.13（本机验证 3.12.3）

需修正的旧描述（来自 Phase -1/0 初稿）：
  - 02 第一节 / 第二节：「fork upstream + git remote rename upstream」→ 改为「vendored 快照 + 不建 upstream remote」
  - 02 第三节：Python 3.11 / pip install -e . → >=3.11,<3.13 / pip install -e ./vendor/bullet-trade
  - 02 第四节：src/bullet_trade、src/quantradar → vendor/bullet-trade + 项目根级扩展包
  - BASELINE：Git remotes（误写 upstream fetch+push）、安装方式、import 路径、验收结论
  - CURRENT_STATE：Provider 状态三分法（源码审计 PASS / Generic Registry / InvestmentDataProvider）

Provider 状态三分法（必须明确区分）：
  - Provider 源码审计：PASS（Phase -1/0 完成）
  - Generic Provider Registry：本阶段实现（IMPLEMENTED）
  - InvestmentDataProvider：NOT IMPLEMENTED（Phase 2）
```

---

# 四、Generic Provider Registry 契约

在 `bullet_trade.data` 暴露：

```python
def register_data_provider(name: str, factory: Callable, *, overwrite: bool = False) -> None:
    """注册外部 Provider 工厂。factory(config: dict) -> DataProvider。"""

def unregister_data_provider(name: str) -> None:
    """注销已注册外部 Provider（清理缓存 + 认证态）。"""
```

规则：

```text
1. 工厂契约：factory(config: dict) -> DataProvider
   config = get_data_provider_config() 与 overrides 的合并（由 _create_provider 传入）
2. _create_provider 仍是唯一创建入口：
   - 先查注册表；命中 → registry_factory(merged_config)
   - 未命中 → 走内置 if 链（jqdata/tushare/...）
   - 未知名称 → ValueError
3. set_data_provider / get_data_provider / reload_data_provider_from_env 全部经 _create_provider，不复制逻辑
4. 内置 Provider 名称受保护：默认禁止外部注册覆盖（需显式 overwrite=True），且不得静默覆盖
5. 认证逻辑（auth）保持不变
6. 内置 Provider 必须仍可独立创建（不被注册表影响）
7. 不实现 InvestmentDataProvider
```

暴露位置：`bullet_trade.data.register_data_provider` / `bullet_trade.data.unregister_data_provider`。

---

# 五、单元测试

新增 `vendor/bullet-trade/tests/unit/test_provider_registry.py`，覆盖（Test 1–7 及扩展）：

```text
T1  注册自定义 Provider 后，set_data_provider(name) / get_data_provider(name) 可用
T2  按名称创建的 Provider 被缓存（同名称返回同一实例）
T3  reload_data_provider_from_env(name) 可按名重建
T4  未知 Provider 名称 → ValueError
T5  重复注册同名（非 overwrite）→ 拒绝；overwrite=True 可覆盖
T6  factory 收到的 config 已合并 overrides
T7  内置 Provider（如 tushare）经 _create_provider 仍可创建，不受注册表影响
T8  内置 Provider 名称受保护（注册同名默认拒绝）
T9  unregister_data_provider 清理缓存与认证态
```

测试层级区分：

```text
- 新测试：test_provider_registry.py（本阶段新增）
- 相关回归：data / provider / auth 相关单测（确认注册表未引入回归）
- 全量：tests/unit 全量（仅用于发现预存无关错误，不要求全绿）
```

---

# 六、验收

完成标志：

```text
CUSTOM_PROVIDER_REGISTRATION_PASS
```

判定：

```text
[PASS] 文档校准：02 / BASELINE / CURRENT_STATE 与 vendor 架构一致
[PASS] Generic Provider Registry 实现（注册 / 注销 / 统一入口 / 内置兼容 / 不静默覆盖）
[PASS] 经 bullet_trade.data 暴露
[PASS] 未硬编码 if target == "investment_data"
[PASS] 未实现 InvestmentDataProvider
[PASS] 单元测试通过（新测试 + 相关回归）
[PASS] 提交单一 commit，message 含验收标志
```

---

# 七、结束条件

```text
1. 控制文档校准完成（02 / BASELINE / CURRENT_STATE / 本文件）
2. 代码实现 + 单元测试通过
3. git diff --check 无遗留空白错误
4. 单一 commit（message 含 CUSTOM_PROVIDER_REGISTRATION_PASS）
5. 更新 CURRENT_STATE / ACTIVE_PHASE 标记 Phase 1 已完成、等待 Phase 2 授权
6. 停止。不自动进入 Phase 2。
```
