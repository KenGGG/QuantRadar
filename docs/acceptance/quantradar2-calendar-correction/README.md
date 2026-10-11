# 交易日历兼容修正：部分执行证据（未完成全区间验收）

本文件保留首次日历修正的部分执行证据。后续用户授权的本地预准备升级已完成完整1681日验收，见[预准备验收](../quantradar2-data-preparation/README.md)；下文当时的阻塞/待验收说明不代表当前活动目标，旧失败任务状态及原始产物未改变。

本次仅在应用 `backend/quantradar2/provider.py` 修正双日期、count=None 的250条默认截断。显式发送含两端自然日数上界，检查范围、严格递增和唯一性；保留显式count及开区间原生语义。未修改QMT/外部BulletTrade、未调用broker、未提交推送。G3未启动。

## TDD / 回归

- `tests/v2/test_provider_calendar.py` 首次RED：旧行为仅返回250日，长区间预期4156日；首次GREEN通过。
- 第二个RED：乱序日历未抛错；添加边界/顺序校验后GREEN。
- 包含超过2000条、显式count、count-only、仅起日/仅止日、无日期、空区间、date/datetime、录制/回放及旧身份拒绝回归。
- Python3.12项目环境，`PYTHONPATH=backend .venv-v2/Scripts/python.exe -B -m pytest tests/v2 -q`：35 passed，1个既有httpx/Starlette弃用警告。

## 唯一新任务及实际阻塞

- strategy：`f46e4c81671c4d8db51df3350fb3bf80`。
- 原revision保持不变：`ec1321ab5cfd4cbbb38aeecc4065ea8e`；GET源与本地/任务源一致。
- 策略SHA256：`9cd954cbedbaaec0e4a7d11f9356d656d6adc7df6d8a59f57d858f9e6ae4ecbc`。
- 新run：`926664c872a14a42a532629700e17468`，GET request与旧run `27abefbb36d148cf97c32f7e09013aaf` 完全一致；2019-01-01至2025-12-05、day、500000、000300.XSHG、record、reference_date2025-12-05及全部extras未改变。
- 原任务与原指标/报告未改写。
- 实际冻结日历请求：start `2019-01-01T00:00:00`、end `2025-12-05T00:00:00`、count2531；响应1681条，2019-01-02至2025-12-05。
- 任务自2026-10-11 09:54:23.978661 UTC运行，到10:24:24.279688 UTC被API默认1800秒上限终止，状态 `FAILED`，error `Task timeout`。不是日历/策略数据错误。启动任务前未充分核验长任务时限，此次不能声称完整回测成功。
- 只完成1404个收盘账户记录，最后2024-10-18；进入2024-10-21（1405/1681）时被终止。最后账户2,460,733.10仅是日志中的中途值，不是2025-12-05最终权益或完整期指标。
- 初始96个交易日全现金500000；首个评分及买入阶段2019-05-29。512890上市前及不足84条warmup正确保持现金，无补齐伪造OHLC。
- 冻结四ETF各1308个完整84条OHLC请求均正数有限、索引严格递增唯一且不超过请求end；512890另有96个初始短/空请求。实际审计至2024-10-17的被使用历史，不能据此宣称后续日期数据质量通过。
- 基准冻结数据包含2018-12-28基价3010.65；2019-01-02价格2969.53，首日收益-1.365818012721498%，与实际首日日志-1.37%一致。日历修正后基准起始不再与2024年模拟起始错位；完整每日CSV比对尚不可做。
- 不存在metrics.json/daily_records.csv，GET artifacts返回0项，GET report为404。没有完整期收益、年化、回撤、Sharpe或最终权益可报告。

## 身份 / 费用假设 / 待验收

- 新adapter fingerprint：`0ee600779291bd5cea4c58621643d4dcc0c092a10568a51a34fa79782dfef4ad`；旧包身份不能冒充新适配回放。
- 外部源fingerprint保持 `0414f86bce593aa0873dedb99baa2b5d4bad8820c352600228f58594971fbf48`，engine SHA `bcc59905f82b35a2f7d73bc876cdf4fb7335b3eaebb7ccd23c9a1b9755390328`；外部工作树干净。
- 原策略基金双向佣金0.0003、最低5、无印花税、FixedSlippage(0.001)；冻结引擎配置market_buy_price_percent0.015、market_sell_price_percent-0.015、strict_data=True。未修改或把FixedSlippage当百分比。
- 原始记录：`var/quantradar2/runs/926664c872a14a42a532629700e17468/`；部分审计：`var/quantradar2/calendar-correction-partial-audit.json`。
- API：http://127.0.0.1:7242/api/v2/runs/926664c872a14a42a532629700e17468 。
- 当前无活动任务。后续需主代理确认追加重跑权限及更长timeout（例如7200秒），按既有v2_stop身份核验流程仅重启API，不动数据服务/QMT，然后保持原请求新建任务并完成1681行CSV、全日期基准、原生指标和报告验收。本子任务遵守“只建一个新任务”，未自动追加第二次任务、未修改manager/runtime时限代码。
