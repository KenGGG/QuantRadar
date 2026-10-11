# QMT本地数据预准备验收

日期：2026-10-11（Asia/Shanghai）。结果：PASS。机器：32逻辑CPU；保留外部BulletTrade 0.10.0与QMT。参考[Qlib数据准备流程](https://qlib.readthedocs.io/en/latest/component/data.html)，采用应用层QMT数据快照，不引入Qlib行情源或改变原生复权/交易规则。

## 实际任务

沿用5053fab22fc24ea29fe970888bd5f785的不可变修订ec1321ab5cfd4cbbb38aeecc4065ea8e、参数、基准与2025-12-05复权参考日；新建任务，不覆盖旧任务。数据清单显式包含4只ETF与84根历史窗口，基准由应用加入。

| 任务 | 总耗时（含原生报告） | 数据准备 | 回测核心 |
| --- | ---: | ---: | ---: |
| 首次183c460311b14371a09cbec982ba29aa | 137.56秒 | 98.43秒 | 29.99秒 |
| 复用80cb8c0f9aa94ae0afe9661b7246f2f4 | 38.79秒 | 0.223秒 | 29.62秒 |
| 回放b2cb643d329f47819e79d1f1d6838850 | 38.38秒 | 不连接QMT | 29.60秒 |

三任务均SUCCEEDED，完整覆盖2019-01-02至2025-12-05的1681个交易日，并生成原生HTML报告。8份CSV逐字节一致；金融指标完全一致，仅忽略生成时间、运行时间、源码路径等非金融元数据。结果、CSV哈希、上市初期现金warmup天数与首个持仓日期见[evidence.json](evidence.json)。

与旧5053fab2已有部分对照：1147个交易日的日志权益/现金/持仓市值（原日志小数两位）一致；1051天因子评分（Python浮点值）、原持仓和调仓选择精确一致。旧任务没有完整CSV，因此不把此日志对照宣称为全区间旧路径CSV验证。

另以2024-01的22个交易日完成真实QMT旧record路径/预准备路径对照，每日权益、持仓、交易CSV逐字节一致，金融指标一致。回测核心分别19.967秒/0.325秒（约61倍），首次准备额外9.56秒；该倍数仅适用于此短样本，不外推为完整区间倍数。

## 数据契约与检查

- 下载覆盖行情窗口和原生引擎辅助日期的日历、none/pre/fixed-reference行情、按回测历史日期查询的证券信息、分红拆分事件；每证券3种视图首/中/尾共45组窗口与QMT精确对照后发布快照。
- 保留QMT指数的字符串索引、字段数值类型和完整浮点精度。参考日是否存在于请求窗口，沿用QMT原生锚定行为；不因提前下载整段行情改变窗口复权结果。
- 每任务独立保存dataset.json及带身份的SHA256 manifest；共享缓存按数据需求/日期/参考日/软件身份复用。命中缓存不调用连接工厂，不读取QMT凭证。刷新共享缓存不改旧任务快照。
- 准备后关闭QMT连接，执行时Provider没有网络连接；未声明或越界查询记入不可清除错误，即使引擎捕获异常也不能最终成功。损坏缓存、身份变化、区间窗口不一致直接失败。
- 预准备范围为固定证券池日频、单证券行情、none/pre复权；其他模式保留旧live/record入口。不把QMT历史证券信息、涨跌停、财务或成分的既有限制宣称为已解决。
- 回测任务和API使用独立日志目录；这三次完整任务stdout没有PermissionError。

## 验证命令与产物

43项tests/v2通过，包含缓存复用、零连接工厂调用、刷新隔离、快照校验、窗口不一致拒绝、上市前空历史、复权参考窗口与双向日期边界测试；前端TypeScript/生产构建通过；pip check通过。只有既有Starlette测试客户端弃用警告和前端大包警告。

```powershell
.venv-v2/Scripts/python.exe -m pytest -q -p no:cacheprovider --basetemp=var/quantradar2/upgrade-tests-final
npm.cmd run build --prefix frontend
.venv-v2/Scripts/python.exe -m pip check
```

实际产物在var/quantradar2/runs/<上述任务ID>；data_preparation.json提供准备/复用计时，metrics.json提供核心耗时，completion.json及SQLite任务状态证明完成，frozen_data.zip包含任务快照。缓存数据对象约9.5MB。完整本机对照汇总保存在var/quantradar2/upgrade-validation/final-summary.json。

API/WebUI已在127.0.0.1:7242运行升级版本，网页默认选择预准备日频；支持填写数据需求JSON及主动重新从QMT准备。现有任务源码、原始报告和记录不被升级覆盖。
