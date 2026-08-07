# 策略测试指南

## 概述

`tests/strategies/` 目录用于存放策略测试用例。你可以在这里添加任意数量的**纯聚宽格式策略文件**，回测参数在 `config.yaml` 中统一配置。

## 核心设计理念

✅ **策略文件保持原汁原味的聚宽格式**  
✅ **回测参数在外部 config.yaml 配置**  
✅ **不修改从聚宽复制来的策略代码**

## 快速开始

### 1. 添加策略文件

直接将聚宽策略复制到 `tests/strategies/` 目录，**无需修改**：

```python
# strategy.my_strategy.py
# 保持聚宽原生导入格式
from jqdata import *

def initialize(context):
    set_benchmark('000300.XSHG')
    run_daily(market_open, time='open')

def market_open(context):
    # 你的策略逻辑
    pass
```

**重要**：策略文件应使用 `from jqdata import *`（聚宽标准格式），而不是 `from bullet_trade.core.api import *`

### 2. 配置回测参数

编辑 `tests/strategies/config.yaml`，为你的策略添加配置：

```yaml
# 策略文件名（不含.py）
strategy.my_strategy:
  start_date: '2023-01-01'
  end_date: '2023-12-31'
  capital_base: 100000
  frequency: 'daily'
  benchmark: '000300.XSHG'
```

### 3. 运行测试

```bash
# 测试所有策略
pytest tests/test_strategies.py -v -s

# 测试特定策略
pytest tests/test_strategies.py -v -s -k "my_strategy"
```

## 配置文件说明

### config.yaml 结构

```yaml
# 默认配置（所有未单独配置的策略使用此配置）
default:
  start_date: '2023-01-01'
  end_date: '2023-12-31'
  capital_base: 100000
  frequency: 'daily'
  benchmark: '000300.XSHG'

# 策略特定配置
strategy_name:  # 策略文件名（不含.py后缀）
  start_date: '2024-01-01'
  end_date: '2024-12-31'
  capital_base: 1000000
  frequency: 'daily'
  benchmark: '000300.XSHG'
  
  # 可选：期望结果约束
  expected:
    total_returns:
      min: 0.05      # 最小总收益率 5%
    max_drawdown:
      max: -0.3      # 最大回撤限制 30%
    sharpe:
      min: 1.0       # 夏普比率至少 1.0
```

### 配置参数说明

| 参数 | 类型 | 说明 | 示例 |
|-----|------|-----|------|
| `start_date` | string | 回测开始日期 | '2023-01-01' |
| `end_date` | string | 回测结束日期 | '2023-12-31' |
| `capital_base` | int | 初始资金 | 100000 |
| `frequency` | string | 运行频率 | 'daily', 'minute', 'tick' |
| `benchmark` | string | 基准指数 | '000300.XSHG' |
| `expected` | dict | 期望结果约束（可选） | 见下文 |

### 期望结果约束（可选）

可以为策略设置性能目标，测试会自动验证：

```yaml
expected:
  total_returns:
    min: 0.0       # 总收益率 >= 0%
    max: 0.5       # 总收益率 <= 50%
  annual_returns:
    min: 0.05      # 年化收益 >= 5%
  max_drawdown:
    max: -0.3      # 最大回撤 <= 30%
  sharpe:
    min: 1.0       # 夏普比率 >= 1.0
  win_rate:
    min: 0.4       # 胜率 >= 40%
```

## 策略文件要求

### 必需的函数

```python
def initialize(context):
    """策略初始化函数，回测开始前调用一次"""
    pass
```

### 可选的函数

```python
def handle_data(context, data):
    """每个交易bar调用（按frequency配置）"""
    pass

def before_trading_start(context):
    """每日交易开始前调用"""
    pass

def after_trading_end(context):
    """每日交易结束后调用"""
    pass

def process_initialize(context):
    """实盘/模拟盘初始化"""
    pass
```

## 示例策略

### 当前可用策略

| 策略文件 | 说明 | 配置位置 |
|---------|------|---------|
| `strategy.joinquant.EPO.py` | ETF动量EPO策略 | config.yaml |
| `simple_ma_strategy.py` | 简单均线策略 | config.yaml |
| `buy_and_hold.py` | 买入持有策略 | config.yaml |
| `a.py` | 用户自定义模板 | config.yaml |

### 添加新策略的步骤

1. **复制策略文件** 到 `tests/strategies/`
   ```bash
   cp ~/my_strategy.py tests/strategies/strategy.my_awesome.py
   ```

2. **编辑 config.yaml** 添加配置
   ```yaml
   strategy.my_awesome:
     start_date: '2023-01-01'
     end_date: '2023-12-31'
     capital_base: 100000
   ```

3. **运行测试**
   ```bash
   pytest tests/test_strategies.py -v -s -k "my_awesome"
   ```

## 使用技巧

### 1. 批量测试多个策略

```bash
# 测试所有策略并生成报告
pytest tests/test_strategies.py -v -s --html=report.html
```

### 2. 对比不同参数

为同一策略创建不同配置：

```yaml
# 配置1：短期回测
strategy.my_strategy.short:
  start_date: '2024-01-01'
  end_date: '2024-06-30'
  capital_base: 100000

# 配置2：长期回测
strategy.my_strategy.long:
  start_date: '2020-01-01'
  end_date: '2024-12-31'
  capital_base: 1000000
```

然后复制策略文件并重命名：
```bash
cp strategy.my_strategy.py strategy.my_strategy.short.py
cp strategy.my_strategy.py strategy.my_strategy.long.py
```

### 3. 调试策略

查看策略详细日志：
```bash
pytest tests/test_strategies.py -v -s -k "my_strategy" --log-cli-level=DEBUG
```

### 4. 快速验证

只测试策略能否运行（不验证结果）：
```bash
# 在 config.yaml 中不设置 expected 约束即可
```

## 常用命令

```bash
# 查看所有可测试的策略
pytest tests/test_strategies.py --collect-only

# 运行所有策略测试
pytest tests/test_strategies.py -v -s

# 运行特定策略（按名称模糊匹配）
pytest tests/test_strategies.py -v -s -k "EPO"

# 并行运行（需要 pytest-xdist）
pip install pytest-xdist
pytest tests/test_strategies.py -v -s -n auto

# 生成HTML报告
pip install pytest-html
pytest tests/test_strategies.py -v -s --html=report.html
```

## 典型工作流

### 场景1: 从聚宽迁移策略

```bash
# 1. 复制策略文件（不修改代码）
cp ~/Downloads/my_joinquant_strategy.py tests/strategies/

# 2. 编辑 config.yaml 添加回测参数
vim tests/strategies/config.yaml

# 3. 运行测试
pytest tests/test_strategies.py -v -s -k "my_joinquant"
```

### 场景2: 快速测试策略想法

```bash
# 1. 编辑 a.py（预留的快速测试文件）
vim tests/strategies/a.py

# 2. 可选：修改 a.py 的配置（在 config.yaml）
vim tests/strategies/config.yaml

# 3. 运行测试
pytest tests/test_strategies.py -v -s -k "^a$"
```

### 场景3: 策略参数优化

```bash
# 1. 为同一策略创建多个配置变体
# config.yaml:
#   strategy.test.v1: { capital_base: 100000, ... }
#   strategy.test.v2: { capital_base: 500000, ... }
#   strategy.test.v3: { capital_base: 1000000, ... }

# 2. 复制策略文件
cp strategy.test.py strategy.test.v1.py
cp strategy.test.py strategy.test.v2.py
cp strategy.test.py strategy.test.v3.py

# 3. 批量测试
pytest tests/test_strategies.py -v -s -k "strategy.test"
```

## 测试输出示例

```
============================================================
测试策略: strategy.joinquant.EPO
文件路径: /path/to/tests/strategies/strategy.joinquant.EPO.py
============================================================

策略配置:
  回测期间: 2024-01-01 ~ 2024-12-31
  初始资金: 1,000,000
  运行频率: daily
  基准指数: 000300.XSHG

回测结果:
  总收益率: 15.30%
  年化收益率: 15.30%
  基准收益率: 8.50%
  阿尔法: 0.0680
  贝塔: 0.7500
  夏普比率: 1.45
  最大回撤: -18.20%
  胜率: 62.00%

============================================================
策略 strategy.joinquant.EPO 测试通过 ✓
============================================================
```

## 常见问题

### Q: 策略需要 from jqdata import * 但测试用 bullet_trade 怎么办？

A: 两种方式都兼容：
- `from jqdata import *` - 聚宽原生API
- `from bullet_trade.core.api import *` - bullet_trade API

测试框架会自动处理API兼容性。

### Q: 如何跳过某个策略的测试？

A: 在配置中添加 `skip: true`：
```yaml
strategy.my_strategy:
  skip: true
  skip_reason: '策略正在开发中'
```

### Q: 可以测试分钟级策略吗？

A: 可以，在配置中设置 `frequency: 'minute'`。

### Q: 配置文件很长怎么办？

A: 可以只配置需要特殊参数的策略，其他使用默认配置。

## 更多信息

- 项目文档: `STRATEGY_TEST_GUIDE.md`
- API参考: `bullet_trade/core/api.py`
- 快速开始: `QUICK_START.md`
