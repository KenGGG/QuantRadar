# ETF三因子动量轮动（文章复现）

## 状态：策略已新增；真实历史回测被行情链路阻塞

2026-10-11 本机执行。不是成功回测，不存在可报告的收益率、年化、夏普、最大回撤或交易数量。

- Strategy ID：`f46e4c81671c4d8db51df3350fb3bf80`
- 最终 revision ID（第2版）：`ec1321ab5cfd4cbbb38aeecc4065ea8e`
- 最终 run ID：`2485937541844c8a96c65c142b74ff0d`，状态 `FAILED`
- 报告入口：`http://127.0.0.1:7242/api/v2/runs/2485937541844c8a96c65c142b74ff0d/report`；实际回读 HTTP 404，尚无报告。
- 源码：`D:/Projects/QuantDev/QuantRadar2/examples/v2/etf_three_factor_article.py`
- 最终源码 SHA256：`9cd954cbedbaaec0e4a7d11f9356d656d6adc7df6d8a59f57d858f9e6ae4ecbc`
- API 回读证据：`var/quantradar2/etf-three-factor-acceptance.json`（本机生成目录，不含凭证）。
- 首次 run `9d8717ed483140b8a14b6b90a6e6dd6b` 对应第1版 `ac0ab14032b2412b8163f42a334482ad`，也因相同连接错误失败；第2版增加预热后历史缺失的显式失败保护。

每次策略 POST/PUT 后均 GET exact strategy/revision 核对源码；每次任务 POST 后均 GET exact run 核对 revision 和参数。最终 readback 包含 FAILED、错误、logs、空 artifacts 及报告 404。未直接写 SQLite。

## 来源及不可确定项

委托上下文提供的文章：猫哥AI量化，2025-12-07，《Claude Code 开发100个量化策略：ETF三因子动量轮动策略（7年13倍）》：
https://mp.weixin.qq.com/s/GPqJrd4UiIKIgCV5DtfLJA

该上下文包含文章公式但没有完整可执行源码。下述缺省值是明确的研究假设，不能冒充作者原版代码或作者已验证的结果。文章提及的约42%/43%年化、夏普大于1.3及10月峰值13倍是作者声称，并未在本机验证。

## 可复现参数和数学定义

固定池（文章未给代码，本实现假设；真实基金名称和上市日期尚无法由QMT验证）：

| 假设对应类别 | 代码 |
| --- | --- |
| 红利低波ETF | 512890.XSHG |
| 创业板50ETF | 159949.XSHE |
| 纳指ETF | 513100.XSHG |
| 黄金ETF | 518880.XSHG |

- `bias_n=60`：close / rolling(bias_n, min_periods=1).mean；取末 `momentum_n=25` 个值并除该段首值，在 x=0..24 上回归，斜率乘10000。
- `slope_n=25`：末25个close除首值，在 x=1..25 上回归；因子为10000 × slope × R²。恒定价格因子为0。
- `efficiency_n=25`：OHLC均值pivot；100 × log(pivot末/首) × abs(log末-log首)/sum(abs(diff(log(pivot))))，路径波动为0时因子为0。
- Z-score 是当日固定池横截面、人口标准差 ddof=0；零方差因子归零。标准化方向是文章未说明项。
- 权重 `weights=[0.3,0.3,0.4]`，`switch_ratio=1.5`，不拟合、不优化文章声称收益。
- 换仓要求候选与当前不同、分数严格领先且 candidate > current × 1.5。分数并列保留已有仓位，无仓时按固定池顺序打破并列。
- 保留 literal 倍数规则，未使用 signed-safe 改版。负当前分时微小领先也可能触发换仓；这是已测试并披露的负分倍数悖论，不是正常的“提升50%”含义。
- 单标的目标权益 `allocation=0.99`，余下1%为费用/整手现金缓冲，是实现假设。无负分现金择时，无相同标的每日再平衡。
- 先卖旧仓再买候选；未完全卖出时不买第二ETF。引擎决定实际成交与费用，非真实交易接口。

全部七项研究参数可通过 API 的 extras 覆盖。未知字段、非整数或小于2的窗口、非三维/负/非有限或不合计为1的权重、无效倍率和分配比例会拒绝。

## 时间、预热和撮合

日频每天09:30调仓；BulletTrade原生 attribute_history('1d') 截止昨日，策略额外断言全部历史日期严格早于当日。使用前复权 fq='pre'，固定参考日期2025-12-05，避免运行日期改变复权基准。skip_paused=False，不跨缺失日用跳停样本补齐。

默认预热长度 max(60+25-1,25,25)=84条。固定池全部满足预热前保持现金，不去掉未预热ETF、不换成其他代码、不缩短研究区间。上市较晚的池成员可能推迟首次交易；确切上市日期及首次满足预热的日期等待真实QMT数据核验。完成预热后任何标的历史长度不足均显式失败；非正/非有限OHLC、重复/乱序/当日日期也失败。数据服务异常传播而不是替换人工数据。

模拟费率：fund买卖佣金0.0003、最低5元，无印花税，FixedSlippage(0.001)。这是原生固定滑点参数，不把它表述为百分比。日频撮合无法保真作者8点打印、±1%限价和分钟成交时序，本文不伪造这些行为。

主任务请求：2019-01-01至2025-12-05，day，初始500000元，000300.XSHG基准，data_mode='record'，reference_date='2025-12-05'，extras显式填写上述默认值。不是把2026年数据拼进原文章7年样本。

## Strict TDD与测试

`tests/v2/test_etf_three_factor.py` 有12个测试：三个因子、横截面标准化、倍率/负分/并列规则、历史校验、初始化/参数覆盖、完整换仓、初期预热、参数拒绝、未成交卖出保护及预热后历史丢失。每个新增行为均先执行预期RED再最小实现GREEN；人工OHLC只用于单元测试，不是实际回测行情。引擎API边界替身用于验证调度及订单顺序，数学计算使用真实函数。

最终全套：

```bash
PYTHONPATH=backend .venv-v2/Scripts/python.exe -m pytest tests/v2 -q
```

实际输出：`30 passed, 1 warning in 8.10s`；警告为已存在的 Starlette TestClient/httpx 弃用提示。显式 PYTHONPATH=backend 防止Hermes宿主Python3.14的site-packages污染项目Python3.12测试解释器。

## 真实运行阻塞与恢复边界

最终源码被真实BulletTrade 0.10.0成功加载，initialize成功。随后在 `provider.get_trade_days` / `data.trade_days` 失败，尚未进入第一个交易日：

```
RemoteServerError: big QMT gateway 不可用: [WinError 10061] 由于目标计算机积极拒绝，无法连接。
```

另行真实请求：512890.XSHG的2018-12日线preview返回502；513100.XSHG的2025-11-03至2025-11-28日线preview也返回502；data-only服务中的 `data.security_info('512890.XSHG')` 同样失败。因此既不能验证代码名称/上市日期，也不能声称拿到了真实OHLC。health中big_qmt_gateway.ready=true并不构成历史数据路径通过，qmt.ready仍false。

需先由有权限者恢复现有data-only服务到BigQMT的请求链路，再以最终revision和相同完整参数创建新record任务、回读状态、原生指标、报告与真实交易产物，才可称回测完成。未重启已有服务、未自动操作QMT GUI、未改QMT/应用/BulletTrade/配置、未新增数据源、未调用broker、未提交或推送Git、未启动G3。
