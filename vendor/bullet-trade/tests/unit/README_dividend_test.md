# 快速测试指南：分红数据一致性

## 🚀 快速开始

### 1. 最快验证（不需要网络，3秒内完成）
```bash
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m unit -v
```

### 2. 测试单个 provider（需要配置环境变量）
```bash
# 测试 jqdata（默认）
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m requires_network -v

# 测试 miniqmt
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m requires_network --live-providers=miniqmt -v

# 测试 tushare
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m requires_network --live-providers=tushare -v
```

### 3. 完整测试（推荐：验证所有 provider 一致性）
```bash
python -m pytest bullet-trade/tests/unit/test_dividend_data_consistency.py -m requires_network --live-providers=jqdata,miniqmt,tushare -v
```

## 📋 预期输出示例

### ✅ 成功案例
```
bullet-trade/tests/unit/test_dividend_data_consistency.py::test_golden_dividends_format PASSED         [ 16%]
bullet-trade/tests/unit/test_dividend_data_consistency.py::test_provider_dividends_match_golden[jqdata] PASSED [ 33%]
bullet-trade/tests/unit/test_dividend_data_consistency.py::test_provider_dividends_match_golden[miniqmt] PASSED [ 50%]
bullet-trade/tests/unit/test_dividend_data_consistency.py::test_provider_dividends_match_golden[tushare] PASSED [ 66%]
bullet-trade/tests/unit/test_dividend_data_consistency.py::test_cross_provider_consistency PASSED      [ 83%]
bullet-trade/tests/unit/test_dividend_data_consistency.py::test_dividend_cash_calculation PASSED       [100%]

============================== 6 passed in 12.34s ==============================
```

### ❌ 失败案例（如果数据不一致）
```
FAILED bullet-trade/tests/unit/test_dividend_data_consistency.py::test_provider_dividends_match_golden[miniqmt]

AssertionError: miniqmt 601318.XSHG 第1个分红事件 (2024-07-26) bonus_pre_tax 不匹配: 期望 15.0, 实际 1.5
```

## ⚙️ 环境变量配置

在 `.env` 文件中配置（至少配置一个）：

```bash
# JQData
JQDATA_USERNAME=your_username
JQDATA_PASSWORD=your_password

# MiniQMT  
QMT_DATA_PATH=C:/path/to/qmt/data

# Tushare
TUSHARE_TOKEN=your_token
```

## 🔍 测试覆盖的场景

| 测试 | 说明 | 需要网络 |
|------|------|----------|
| `test_golden_dividends_format` | 验证黄金标准数据格式 | ❌ |
| `test_provider_dividends_match_golden` | 验证各 provider 与黄金标准一致 | ✅ |
| `test_cross_provider_consistency` | 验证所有 provider 相互一致 | ✅ |
| `test_dividend_cash_calculation` | 验证现金计算公式 | ❌ |

## 📊 测试的分红数据

| 证券 | 日期 | per_base | bonus_pre_tax | 说明 |
|------|------|----------|---------------|------|
| 601318.XSHG | 2024-07-26 | 10 | 15.0 | 每10股派15元 |
| 601318.XSHG | 2024-10-18 | 10 | 9.3 | 每10股派9.3元 |
| 511880.XSHG | 2024-12-31 | 1 | 1.5521 | 每1份派1.5521元 |

## 💡 常见问题

### Q1: 为什么我的测试被跳过了？
A: 检查环境变量是否配置，测试会自动跳过未配置的 provider。

### Q2: 如何只测试我关心的 provider？
A: 使用 `--live-providers` 参数指定，例如：
```bash
python -m pytest ... --live-providers=miniqmt
```

### Q3: 测试失败了怎么办？
A: 查看错误信息中的期望值和实际值，修复对应 provider 的 `get_split_dividend` 方法。

### Q4: 可以在 CI/CD 中运行吗？
A: 可以！确保 CI 环境配置了必要的环境变量和依赖包。

## 📚 相关文档

- 完整文档：`test_dividend_data_consistency.md`
- 实现代码：
  - `bullet_trade/data/providers/jqdata.py`
  - `bullet_trade/data/providers/miniqmt.py`
  - `bullet_trade/data/providers/tushare.py`

