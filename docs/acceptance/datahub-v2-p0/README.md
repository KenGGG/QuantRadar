# DataHub V2 P0 inventory evidence

The inventory was generated on 2026-09-11 from fixed release
`Re7a88349f47a53e4`, base commit `uhdpedb4pr97ve80aq6nrabr66atsqtq`.
The machine-readable report is `/data/quantradar_data/base_inventory.json`;
the corresponding low-Beta window work item is
`/data/quantradar_data/gap_plan.json`.

## Observed base material

| Domain | Chosen material | Reusable material / status | Observed range |
| --- | --- | --- | --- |
| Raw daily price | `final_a_stock_eod_price` | BaoStock, Tushare and Wind/财汇 tables are present | 1990-12-19 to 2026-09-11; 18,454,486 rows |
| ST / status | `bao_a_stock_eod_info` | PARTIAL | 1990-12-19 to 2023-06-09; 14,342,735 rows |
| Lifecycle | `ts_a_stock_list` | PARTIAL | listing dates through 2022-07-18; 5,023 rows |
| Trade calendar | `ts_trade_day_calendar` | VALID | 1990-12-19 to 2026-12-31 |
| Index weights | `ts_index_weight` | PARTIAL | 2005-04-08 to 2026-08-31; 2,402,036 rows |

Price volume is stored in hands and amount in thousand yuan.  This is a source
contract fact, not a post-fusion conversion instruction; the strategy release
continues to normalize at its existing read boundary.

## CSI 300 identity check

`000300.SH` has 18,300 stored rows from 2020-01-02 through 2022-07-01.
`399300.SZ` has 560,394 rows from 2005-04-08 through 2026-08-31.  On all 47
common stored snapshots both have exactly 300 constituents and the constituent
sets are equal.  The evidence permits a versioned alias only for
2020-01-02 through 2022-07-01. It does not demonstrate an alias outside that
overlap.

## Low-Beta window plan

The actual historical low-Beta run uses 2020-01-01 through 2026-08-31.
Price coverage satisfies this window from the selected base table and creates
no network work. The broad range-level status gap is 2023-06-10 through
2026-08-31, marked `UNKNOWN` under `base-bao-daily-v1`; it is not a claim that
every stock and date in that interval lacks data. Later P3 work filled the
11,400 exact low-Beta dependency keys with a released BaoStock patch. The
remaining broad range stays unknown until a strategy asks for specific keys.

This is P0 inventory evidence. AKShare Tencent price remains only
`QUALIFIED_SAMPLED` and has not altered a published release. BaoStock has since
been used only for the separately accepted low-Beta status patch; it is not a
claim of whole-market status completeness.
