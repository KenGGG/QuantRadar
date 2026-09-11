# DataHub V2 实施验收矩阵

验收日期：2026-09-12。此矩阵验证 V2 方案的工程流程和已观察到的数据范围；`PARTIAL`、隔离项和来源边界保持原样，不被解释为全市场数据完整。

| 场景 | 结论 | 证据 |
| --- | --- | --- |
| A01–A04 存量复用、别名、内部缺口、增量 | 通过 | 固定 release 库存与缺口计划；`test_inventory_*`、`test_index_alias_requires_equal_constituents_on_every_overlap`、`test_sync_watermark_*` |
| A05–A08 BaoStock 多域、预算、限流、解析失败 | 通过 | `test_baostock_bundle_keeps_status_and_never_maps_ncf_to_ocf`、`test_request_governor_*`、`test_adapter_parse_error_*`；三证券实测健康探针为解析异常，无限流证据 |
| A09–A12 域隔离、单位、三态、OCF 语义 | 通过 | `test_pipeline_leaves_current_release_untouched_when_one_dataset_fails`、`test_new_units_*`、`test_paused_keeps_unknown_*`、`test_baostock_pe_pb_ps_candidate_*` |
| A13–A15 复权、过期成分、历史证券 | 通过，PIT 限制保留 | `test_backtest_fq.py`、`test_jq_compat.py`、`test_lifecycle_as_of_never_excludes_a_security_before_known_delisting`；CSI 300 后 2022-07-01 历史仍为 PARTIAL |
| A16–A18 同源说明、冲突、版本隔离 | 通过 | `source_contracts.yaml` 明确基础 BaoStock 与新 BaoStock 的相关性；`test_status_patch_validation_*`、`test_get_extras_cache_isolated_by_release`、`tests/integration/test_datahub_dolt.py`（2 passed） |
| A19–A20 固定回测、来源解释、实际 usage | 通过 | R22 完整回测无网络采集；`run_4acb95f4946a440abc7b924fea7af4aa` 的快照记录双 commit 与实际读取计数；数据状态页由后端 `data_sources` 统一返回 |
| A21–A24 连接故障、差异、队列、不可得范围 | 通过 | `test_provider_database_errors_cannot_be_swallowed_as_an_empty_universe`、状态补丁回放证据、`test_work_queue_*`、显式 `FAILED`/`NOT_COVERED`/`UNKNOWN` 台账 |

## 实测发布与回测

- 当前 release：`R22a53f013266373d`。
- 低 Beta 策略依赖的 38 个状态日期已发布 11,347 条 BaoStock 补数；298 个证券完成，2 个证券因基础行情先结束而为 `NOT_COVERED`。
- 严格低 Beta 在 2020-01-01 至 2026-08-31 的 1,615 个交易日回测 `SUCCESS`，结果哈希为 `49849a788b8b506c4430264d73153c2e2a35bee7e6480bf3c2b095f6162a0484`。详见 `datahub-v2-p3/low-beta-r22-full-backtest.md`。

## 保留的数据限制

- 估值 196 个证券仍是 AKShare 1.18.94 的同类 `NoneType` 解析异常；三证券受控探针未发现限流或网络问题，未批量重试。
- 123 个估值范围缺少覆盖证据，仍为 `NOT_COVERED`。
- 2022-07-01 之后的 CSI 300 成分历史完整性、严格 PIT、跨源数值一致性和完整生命周期字段覆盖仍是 `PARTIAL`；页面和 release 元数据均保留此状态。
- 基础行情不存在已验证的生产缺口，因此腾讯行情保持 `QUALIFIED_SAMPLED`，未凭人工制造缺口发布补丁。
