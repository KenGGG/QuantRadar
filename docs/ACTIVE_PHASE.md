# QuantRadar 当前开发任务

文件：`docs/ACTIVE_PHASE.md`

**当前阶段：Phase 1.1 — Provider Registry 生命周期加固（已完成 / 等待下一阶段授权）**

阶段标志：`PROVIDER_REGISTRY_LIFECYCLE_PASS`

```text
本阶段已完成：
  1. 补齐 unregister_data_provider 显式测试（T10）
  2. 修复 overwrite=True 的 cache 一致性（注册即清该名称 instance cache + auth state）
  3. 明确 active global provider 最小原则（unregister/overwrite 不热切换全局 _provider）
  4. 确认并文档化 bootstrap 契约（import 阶段 _create_provider；QuantRadar 需自有 bootstrap 层）
  5. 测试 13/13 通过；相关 data/provider/auth 回归无新增失败
禁止自动进入 Phase 2 / 2A。下一阶段需显式授权。
```

---

# 一、目标

Phase 1 的 Generic Provider Registry 已成立。本阶段只解决三个生命周期问题：

```text
1. unregister 行为缺少完整测试
2. overwrite 后 Provider cache 一致性
3. 明确 QuantRadar 外部 Provider 的启动 / bootstrap 契约
```

不得实现 InvestmentDataProvider。

---

# 二、范围与边界（强制）

```text
允许：
  - 修改 vendor/bullet-trade/bullet_trade/data/api.py（register/unregister 的 cache/auth 清理 + docstring）
  - 新增/补齐 vendor/bullet-trade/tests/unit/test_provider_registry.py（T10–T13）
  - 更新 docs/03_数据与Provider规范.md（bootstrap 契约 + 配置边界）
  - 更新 docs/CURRENT_STATE.md（生命周期状态 + bootstrap DESIGN READY）

禁止：
  - 实现 InvestmentDataProvider / Dolt Connection / symbol mapper / get_price 等数据能力
  - 重构 BulletTrade 全局 Provider 初始化机制（_provider = _create_provider() 保持原样）
  - 实现 lazy provider / entry-point plugin discovery
  - 在 vendor/bullet-trade/bullet_trade/utils/env_loader.py 硬编码 investment_data 专属配置
  - 自动进入 Phase 2 / 2A
```

---

# 三、unregister 测试（T10）

```python
register_data_provider("dummy", factory)
p = get_data_provider("dummy")
# 断言：dummy in _PROVIDER_REGISTRY / _provider_cache / _provider_auth_attempted
unregister_data_provider("dummy")
# 断言：三者均 not in
```

不得仅经 fixture 间接调用 unregister 而无断言。

---

# 四、overwrite cache 一致性（T11）

```text
register(name, factory_v1)  → get_data_provider → provider_v1
register(name, factory_v2, overwrite=True)
get_data_provider → provider_v2  （新 factory 新实例）
要求：provider_v2 is not provider_v1
```

实现：注册（含 overwrite）时清除该名称既有 `_provider_cache` 与 `_provider_auth_attempted`。

---

# 五、active global provider 最小原则

```text
unregister / overwrite 的对象恰好是当前全局 _provider 时：
  - Registry / cache 负责「未来按名创建」
  - 当前已激活的全局 _provider 不自动替换
  - 切换当前 Provider 必须显式 set_data_provider(...)
  - 不在 unregister 内隐藏切换行为
```

（由 T13 验证；docstring 与文档写明。）

---

# 六、bootstrap 契约（已确认 + 文档化）

```text
_provider = _create_provider() 发生在 bullet_trade.data.api 模块 import 阶段
→ 此时 Registry 为空，按 DEFAULT_DATA_PROVIDER 走内置 if 链
→ 不保证 DEFAULT_DATA_PROVIDER=investment_data 在注册前自动成功
```

不重构 BulletTrade 初始化机制、不实现 lazy / entry-point。

QuantRadar 正式 bootstrap 顺序（写入 03）：

```text
启动 QuantRadar
→ import BulletTrade
→ register_data_provider("investment_data", factory)
→ set_data_provider("investment_data")
→ 验证 get_data_provider().name == "investment_data"
→ 才允许数据查询 / 回测
```

QuantRadar 不依赖 `DEFAULT_DATA_PROVIDER=investment_data` 在 import 阶段自动注册。该 bootstrap 层在 Phase 2 创建。

---

# 七、配置边界（已写入 03）

```text
get_data_provider_config() 只定义内置 Provider 配置
InvestmentDataProvider 配置不得硬编码进 env_loader.py
QuantRadar 自己管理 INVESTMENT_DATA_HOST/PORT/USER/PASSWORD/DATABASE（或等价 DSN）
factory(InvestmentDataProvider(config)) 从 QuantRadar 配置构造
Registry 只负责 名称 → factory；BulletTrade 不负责理解 investment_data 专属配置
```

---

# 八、测试

```text
T10 unregister 清 Registry/cache/auth（显式断言）
T11 overwrite 清旧 cache，使用新 factory（provider_v2 is not provider_v1）
T12 unregister 当前缓存 Provider 后按名重新获取明确失败
T13 当前 active global provider 不因 unregister 自动偷偷切换
原 Phase 1 Registry 测试（T1–T9）继续全部通过
```

运行：

```text
test_provider_registry.py（13/13）
data/provider/auth 相关回归（无新增失败）
```

---

# 九、验收

完成标志：`PROVIDER_REGISTRY_LIFECYCLE_PASS`

```text
[PASS] unregister 显式测试（T10）
[PASS] overwrite cache 一致性（T11）
[PASS] active global 不热切换（T13）+ bootstrap 契约文档化（03/CURRENT_STATE）
[PASS] 原 Phase 1 测试继续全过（T1–T9）
[PASS] 未实现 InvestmentDataProvider；内置 Provider 创建/认证不变
[PASS] 单一 commit，message 含 PROVIDER_REGISTRY_LIFECYCLE_PASS
```

---

# 十、结束条件

```text
1. 生命周期修复 + 测试（T10–T13）
2. docs/03 + CURRENT_STATE 更新（bootstrap 契约 / 配置边界 / 状态）
3. git diff --check 无遗留空白错误
4. 单一 commit（含 PROVIDER_REGISTRY_LIFECYCLE_PASS）
5. 更新 CURRENT_STATE / ACTIVE_PHASE 标记 Phase 1.1 已完成、等待下一阶段授权
6. 停止。不自动进入 Phase 2 / 2A。
```
