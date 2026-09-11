# DataHub 整改验收（2026-09-11）

本次按用户提供的整改意见在 `main` 实施；Web 服务也已切到主工作区。没有删除旧 worktree、强推远端或覆盖基础表。

## 失败对账与来源边界

真实配置台账：`/data/quantradar_data/journals/valuation_daily-mvp.json`。
原始快照见 `journal-baseline.json`，逐项清单见 `baseline_failures.csv`，分类见 `failure_groups.json`。
基线 SHA256：`ea8485e3e016509996134cfeb9f30e1204e8bc9c3f02ad80d8709720da95e374`。

| 类别 | 基线 | 本轮处置 |
|---|---:|---|
| COMPLETE | 5,235 | 全量扫描候选文件，合格者允许发布 |
| FAILED | 196 | 均保留隔离；修复 0、删除 0、改成无覆盖 0 |
| 旧 NOT_COVERED | 123 | 缺少原始覆盖证明，按 UNVERIFIED_COVERAGE 隔离 |
| 总证券 | 5,554 | 分母保持不变 |

196 项均为 `akshare.stock_value_em` / `akshare-1.18.94` 的 `TypeError: 'NoneType' object is not subscriptable`。
已安装 SDK 在 `data_json["result"]["data"]` 直接索引返回结果；旧台账未保存这些失败的 HTTP 原文，不能据此断言退市、合法空值或来源永不覆盖。
相同版本不再自动批量重复请求；CLI 可指定最多三个现有失败证券做受控诊断。历史未知尝试次数、失败时间仍标 UNKNOWN。

本轮有限增量抓取增加了 50 行，来自此前已经 COMPLETE 的证券；这不是修复了 50 项失败。
SDK 数据帧 CSV 和旧标准化文件归档均不冒充原始 HTTP 字节。
BaoStock 的冻结失败、原文及旧 NCF 版本保留；不用于新 OCF 规范。

## 检查与发布规则

实际流式检查内容哈希、行数、类型、有限数值、重复主键、股票/日期格式、来源口径、适配器与归档证据。报告绑定候选 ID、基础 commit、策略版本和输入哈希；写入前再次核对输入。
交易日历检查会发现中间缺日，不能只用首尾日期宣称完整。
候选质量通过与覆盖/PIT 完整是不同维度。跨源数值一致性、历史可得时点和完整生命周期×字段覆盖仍为 NOT_CHECKED。

初次只读检查：5,235 只、9,206,942 行通过，319 只隔离，格式错误 0、重复主键 0。
正式发布验证使用更新后的 9,206,992 行；当前指针只有在固定补充 commit 的实际表统计检查后才切换。
旧版本 `Rb60ab5f94b2a612b` 原估值为 3 只 / 4,359 行，旧口径不被称为新接口可用。

已在隔离候选分支写入并校验固定 supplemental commit 后，将 current release 原子切换为 `Re7a88349f47a53e4`：估值 5,235 只、9,206,992 行，日期 2018-01-02 至 2026-09-11；行业保留 5,568 只、12,536 行；当前获准基础资料 4,916 只。再次发布相同候选返回 `NO_CHANGE`，见 `idempotency.json`。

## 两库更新与用户操作

日常只需点击 **更新全部数据**。基础同步、估值、行业、基础资料、检查、发布均有结果；细节操作折叠。
UI、CLI `update-all` 和 timer 调用同一协调器，重复启动返回 ALREADY_RUNNING。
定时服务使用 `update-all --wait`，避免 oneshot 退出导致后台子进程被停止。

基础库 Dolt 1.86.0、master、干净工作区、可信 origin 已核对。只读 SQL 的 DOLT_PULL 返回 read-only；代码支持在没有回测读锁/排队任务时短暂维护，以 CLI `pull --ff-only` 同步后恢复只读服务。脏工作区、分叉或失败均保留旧版本；不做 reset。
维护同步实际 fast-forward：`dje7kjb4gb27khhfmqncnfhf00n9igcg` → `uhdpedb4pr97ve80aq6nrabr66atsqtq`，之后只读服务恢复。同步后的行情为 5,556 只、18,171,885 行，最新 2026-09-11；ST/停牌仍为 5,183 只、最新 2023-06-09，页面单列为部分覆盖，不能被行情最新日期掩盖。

固定基础 commit `dje7kjb4gb27khhfmqncnfhf00n9igcg` 的沪深 A 股统计：行情 5,553 只 / 18,156,265 行，至 2026-09-08；ST/停牌 5,183 只，至 2023-06-09；基础名录 4,916 只，最新上市日期 2022-07-15。上市日期不是名录刷新日期。
行业暂无已验收增量入口，明确 SOURCE_BLOCKED、保留旧记录；基础名录只使用固定基础版本，不推断上市/退市时间。

sync 对每股目标交易日记录检查水位，识别 COMPLETE 之后的新交易日，并重检数值修订；源 API 传输仍为每股全历史。backfill 接收必填历史范围并检查边界/已审计内部缺日；同范围无变化不会无限重抓。resume 继续未完成工作；repair 按失败原因处理。
经济内容相同不产生 release；仅 fetched_at 改变不制造 Dolt 业务修订。后续候选从合格发布 commit 建分支，只写变化证券。

## 策略读取与验证

策略无需选择两个目录。行情来自固定基础 commit；支持的 `get_fundamentals` 估值和 `get_industry` 一级行业来自配对的补充 commit。
估值仅支持明确股票池的 code / pe_ratio / pb_ratio / ps_ratio 查询。缺必需记录、字段或隔离证券会报错，不缩小用户股票池；其他财务表、任意联表和未支持口径明确拒绝。
`query.quantradar_require_pit = True` 会拒绝 PARTIAL PIT；未要求严格 PIT 的读取也保留 PARTIAL 标记。

| 验证 | 结果 |
|---|---|
| 整改单测 + 临时 Dolt 集成 | 72 passed（含哈希篡改、未知空响应、冷却、台账竞争、候选隔离、时间戳幂等） |
| 基础 Provider / bootstrap / 聚宽兼容真库只读 | 31 passed |
| 前端 TypeScript + Vite 构建 | PASS；已有大 bundle 提示 |
| 买入持有，不复权 | PASS，6.017 秒，结果哈希不变 |
| 买入持有，前复权 | PASS，5.349 秒，结果哈希不变 |
| 低 Beta 历史 release 回放 | PASS，51.069 秒，结果哈希与既有基线完全相同 |
| 新版补充字段实际读取 / 浏览器发布刷新 | PASS：估值与一级行业可读；隔离证券、缺失日期和严格 PIT 均明确报错；页面自动显示新版本 |
| 新旧 release 并发回放 | PASS：每次记录自己的 release、base/supplemental commit 与单位版本，不串数据 |

三个回测详情见 `backtests.json`。低 Beta 先前优化样例为 37.22 秒；本次首次重启后回放为 51.069 秒，热缓存复测为 46.812 秒，其中 39.819 秒来自 1,578 次本地 Dolt SQL 查询。结果未退化，但速度没有达到此前优化基线；性能后续应减少重复行情、状态和证券生命周期查询，而不是优化网络。两个买入持有样例的期间没有导致结果差异的公司行动，因此相同哈希不等于所有复权区间等价。
新 release 还修正行情单位：原表 volume 为手、amount 为千元；新策略接口输出股和元。15 个价格区间样本、9 个独立历史字段交叉样本均通过，详情见 `price-unit-summary.json` 与 [字段契约](../../datahub-contract.md)。旧 release 保持 legacy 单位回放，不能与新版单位混用。
原生可选 PNG 导出提示不可用；HTML 回测报告已生成。跨源数值核对、严格历史 PIT 和完整市场覆盖未获通过，不以本轮工程测试代替。
