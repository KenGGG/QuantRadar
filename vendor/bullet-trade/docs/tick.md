# Tick 订阅与行情接收指南

面向实盘/远程使用者的 Tick 使用说明，覆盖订阅、接收、取消以及当前实现限制。

## Tick 订阅架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Tick 订阅数据流架构                                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  场景 A: 本地 xtdata 订阅（Windows + miniQMT 环境）                            │
│                                                                             │
│  ┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐   │
│  │   策略代码        │      │   bullet-trade    │     │   miniQMT        │   │
│  │                  │      │   core/api.py    │      │   xtquant SDK    │   │
│  │  subscribe(      │      │                  │      │                  │   │
│  │   ['000001'],    │─────▶│  subscribe()     │─────▶│ xtdata.subscribe │   │
│  │   'tick'         │      │                  │      │ _quote()         │   │
│  │  )               │      │                  │      │                  │   │
│  └──────────────────┘      └──────────────────┘      └────────┬─────────┘   │
│                                                               │             │
│                                                   实时推送 tick│             │
│                                                               ▼             │
│  ┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐   │
│  │   handle_tick    │◀─────│   _on_xt_tick    │◀─────│ callback 回调    │   │
│  │   (context,tick) │      │   字段映射转换     │      │ {lastPrice,time} │   │
│  │                  │      │   sid/last_price │      │                  │   │
│  └──────────────────┘      └──────────────────┘      └──────────────────┘   │
│                                                                             │
│  特点：延迟最低（< 100ms），支持全市场订阅 ['SH','SZ']                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  场景 B: LiveEngine + qmt-remote 远程订阅（macOS/Linux 客户端）                 │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  客户端 (macOS/Linux)                                                 │   │
│  │                                                                      │   │
│  │  ┌──────────────┐    ┌──────────────────┐    ┌────────────────────┐  │   │
│  │  │  策略代码     │    │  LiveEngine       │    │ RemoteQmtBroker   │  │   │
│  │  │              │    │                  │    │ RemoteQmtProvider  │  │   │
│  │  │  subscribe(  │───▶│ register_tick_   │───▶│                    │  │   │
│  │  │   [...],     │    │ subscription()   │    │ 记录订阅清单         │  │   │
│  │  │   'tick'     │    │                  │    │                    │  │   │
│  │  │  )           │    │                  │    │                    │  │   │
│  │  └──────────────┘    └──────────────────┘    └────────────────────┘  │   │
│  │                              │                         │             │   │
│  │                   tick_sync_interval                   │             │   │
│  │                   (默认 2 秒轮询)                        │             │   │
│  │                              │                         │             │   │
│  │                              ▼                         │             │   │
│  │                      ┌──────────────────┐              │             │   │
│  │                      │  _tick_loop()    │              │             │   │
│  │                      │  定时拉取快照     │───────────────┘             │   │
│  │                      └────────┬─────────┘                            │   │
│  │                               │                                      │   │
│  │                               │ request("data.snapshot")             │   │
│  └───────────────────────────────┼──────────────────────────────────────┘   │
│                                  │                                          │
│                          ════════╪════════  网络 ════════════════            │
│                                  │                                          │
│  ┌───────────────────────────────┼──────────────────────────────────────┐   │
│  │  服务端 (Windows + miniQMT)    │                                      │   │
│  │                               ▼                                      │   │
│  │  ┌────────────────────────────────────────────────────────────────┐  │   │
│  │  │  bullet-trade server                                           │  │   │
│  │  │                                                                │  │   │
│  │  │  ┌────────────────┐       ┌────────────────┐                   │  │   │
│  │  │  │ QmtDataAdapter │◀──────│ data.snapshot  │◀── 客户端请求       │  │   │
│  │  │  │                │       │ 处理器          │                   │  │   │
│  │  │  └───────┬────────┘       └────────────────┘                   │  │   │
│  │  │          │                                                     │  │   │
│  │  │          │ get_current_tick()                                  │  │   │
│  │  │          ▼                                                     │  │   │
│  │  │  ┌────────────────┐                                            │  │   │
│  │  │  │ xtdata.get_    │                                            │  │   │
│  │  │  │ full_tick()    │                                            │  │   │
│  │  │  └───────┬────────┘                                            │  │   │
│  │  │          │                                                     │  │   │
│  │  │          ▼                                                     │  │   │
│  │  │  ┌────────────────┐                                            │  │   │
│  │  │  │ miniQMT        │  实时 tick 数据源                            │  │   │
│  │  │  │ xtquant SDK    │  {lastPrice, time, bidPrice, askPrice...}  │  │   │
│  │  │  └────────────────┘                                            │  │   │
│  │  └────────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  特点：跨平台支持，延迟 = tick_sync_interval + 网络延迟                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  handle_tick 回调数据格式                                                     │
│                                                                             │
│  def handle_tick(context, tick):                                            │
│      # tick 字典包含以下字段（来源于 miniQMT xtdata 推送）                       │
│      tick = {                                                               │
│          'sid': '000001.XSHE',       # 聚宽风格代码                           │
│          'symbol': '000001.SZ',      # QMT 风格代码                          │
│          'last_price': 10.50,        # 最新价                                │
│          'dt': 1700000000000,        # 时间戳(毫秒)                           │
│          # ── 盘口字段（本地 xtdata 模式可用）──                                │
│          'bid1': 10.49,              # 买一价                                │
│          'ask1': 10.51,              # 卖一价                                │
│          'bid1_volume': 1000,        # 买一量                                │
│          'ask1_volume': 800,         # 卖一量                                │
│          'last_close': 10.30,        # 昨收                                  │
│          'open': 10.35,              # 开盘价                                │
│          'high': 10.55,              # 最高价                                │
│          'low': 10.28,               # 最低价                                │
│          'volume': 50000,            # 成交量                                │
│          'amount': 525000.0,         # 成交额                                │
│      }                                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

底层实现主要有两条链路：

- **LiveEngine + qmt-remote（默认）**：`subscribe(...)` 只记录订阅清单，后台按 `tick_sync_interval`（默认 2 秒）轮询券商的 `get_current_tick`。对于远程场景，该调用会通过 `RemoteQmtBroker -> RemoteQmtConnection` 请求 server 的 `data.snapshot`，并在收到后触发策略的 `handle_tick`。
- **本地 xtdata（无 LiveEngine 或设置了 xtdata 数据源）**：`subscribe(...)` 会直接调用 `xtdata.subscribe_quote/subscribe_whole_quote` 由 xtquant 推送，回调 `_on_xt_tick` 统一成 `sid/last_price/dt` 后传给策略的 `handle_tick`。
- **Server 端 data.subscribe**：`bullet-trade server` 内部的 `TickSubscriptionManager` 每隔 1 秒轮询数据适配器的 `get_current_tick`，将结果打包成事件 `{"symbol": "000001.SZ", "sid": "000001.XSHE", "last_price": 10.1, "dt": ...}` 推给远程客户端。当前 LiveEngine 的 qmt-remote 券商并不消费该推送，而是采用上面的轮询模式。

### Tick 负载里有哪些字段？
- 始终有 `sid`（聚宽风格代码，例如 `000001.XSHE`）和 `last_price`、`dt`（时间字符串）。  
- xtdata 推送时原始字段是 `stock_code`/`code` + `lastPrice`/`time`，框架会映射成上述键；server 推送时会额外带 `symbol`（QMT 风格代码，如 `000001.SZ`）。  
- **本地 xtdata 订阅** 会尽量保留盘口与昨收等字段：`bid1/ask1/bid1_volume/ask1_volume/last_close/open/high/low/volume/amount/limit_up/limit_down`，命中即写入 `tick`；五档以上暂未展开。  
- 远程 qmt-remote 目前仍只有基础快照（不含盘口深度）。

## 快速开始：订阅部分标的
1. 准备 `.env.live`（或通过 `--env-file` 指定），关键项：  
   `DEFAULT_BROKER=qmt-remote`、`QMT_SERVER_HOST/PORT/TOKEN`，必要时 `QMT_SERVER_ACCOUNT_KEY`、`QMT_SERVER_SUB_ACCOUNT`、`QMT_SERVER_TLS_CERT`。  
   服务端需已通过 `bullet-trade server --enable-data --enable-broker` 启动。
2. 在策略中声明订阅并实现回调：
   ```python
    import datetime as dt
    from jqdata import *


    def initialize(context):
        pass


    def process_initialize(context):
        subscribe(['000001.XSHE', '000002.XSHE','232592.XSHG','104749.SZ'], 'tick')


    def handle_tick(context, tick):
        """
        假定 tick 是 dict，形如 {code: [payload,...]} 或 {code: payload}。
        只提取最常用字段并打印当前时间与 tick 时间的延迟。
        """
        now = dt.datetime.now()
        if not isinstance(tick, dict):
            log.info(tick)
            return

        for code, payload in tick.items():
            entry = payload[0] if isinstance(payload, (list, tuple)) and payload else payload
            if not isinstance(entry, dict):
                log.info(f"code={code} tick={entry}")
                continue
            ts_raw = entry.get('time') or entry.get('datetime')
            delay = ""
            if isinstance(ts_raw, (int, float)):
                try:
                    delay_val = (now - dt.datetime.fromtimestamp(ts_raw / 1000)).total_seconds()
                    delay = f"[delay=+{delay_val:.3f}s] "
                except Exception:
                    delay = ""
            log.info(
                f"{delay}code={code} last={entry.get('lastPrice')} "
                f"bid={entry.get('bidPrice')} ask={entry.get('askPrice')} "
                f"vol={entry.get('volume')} amt={entry.get('amount')} ts={ts_raw}"
            )

   ```
3. 启动实盘：  
   `bullet-trade live strategies/demo.py --broker qmt-remote --env-file .env.live`
4. 运行中可随时调用 `unsubscribe(['000001.XSHE'], 'tick')` 或 `unsubscribe_all()` 取消。

能从图上看到我们测试环境tick数据的延迟情况
![delay](assets/tick-delay.png)


> 轮询模式意味着订阅数量越多，对 server 的请求压力越大；请留意 `tick_subscription_limit`（默认 100）和 `tick_sync_interval`。

### 重启 / 热更新后的订阅要点
- LiveEngine 会把订阅清单持久化，但券商侧不会自动恢复订阅。若第二次启动时跳过了 `initialize`，订阅不会自动重绑。
- 建议在 `process_initialize`（Live 独有）或 `after_code_changed` 中再调用一次 `subscribe(...)` 以确保重启/热更新后仍然生效；也可在 `initialize` 里保留调用以兼容回测。

## 全市场订阅
- 本地 Windows + xtquant 场景可用：`subscribe(['SH', 'SZ'], 'tick')` 会调用 `xtdata.subscribe_whole_quote`，推送经 `_on_xt_tick` 转发后进入 `handle_tick`。
- **远程 qmt-remote 暂不支持全市场订阅**：server 端未实现 `allow_full_market` 开关，`RemoteQmtBroker` 也未对接推送订阅；需要全市场时只能在本地 xtdata 运行或自行枚举标的列表。

## 取消与查询
- `unsubscribe([...], 'tick')`：取消部分订阅；`unsubscribe_all()`：全部取消。对远程模式会减少 LiveEngine 轮询列表。
- `get_current_tick('000001.XSHE')`：即时拉取一次快照（同样经 server 的 `data.snapshot` 拉取），不依赖订阅状态，可在调试时验证连通性。

## 已知限制与测试现状
- 推送链路与 LiveEngine 脱节：远程模式的订阅不会触发 server 端的 tick 推送，而是客户端每隔 `tick_sync_interval` 主动拉取；标的较多时延迟与带宽占用上升。
- 未实现 Throttler/压缩/批量：server 端对订阅数仅做上限校验，没有批量聚合或压缩，极端高频场景需要谨慎。
- 全市场订阅仅限本地 xtdata；`allow_full_market` 配置未在 server 侧生效。
- 自动补价/停牌检测仅在下单时发生，tick 本身不含这些标志。
- 测试覆盖：存在 LiveEngine 订阅限额与快照读取的单测（见 `tests/core/test_live_engine.py`），但没有覆盖远程 server 的 tick 订阅/推送、重连、全市场等场景；建议实盘前手工验证。
