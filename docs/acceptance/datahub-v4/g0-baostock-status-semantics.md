# G0 BaoStock 状态字段语义探针

Probe date: 2026-09-15 (Asia/Shanghai).  The probe used the repository's
`BaostockAdapter.daily_bundles()` and queried BaoStock only; it did not stage,
publish, or modify either Dolt repository.

| Case | Symbol / dates | Observed result | Expected-key treatment |
| --- | --- | --- | --- |
| Normal trading | `600519.SH`, 2023-03-01 | `tradestatus=1`, `is_st=0`, `turn=0.1947` | both state fields required and present |
| ST trading | `600078.SH`, 2023-03-01 | `tradestatus=1`, `is_st=1`, `turn=1.7241` | both state fields required and present |
| Continuous suspension | `000039.SZ`, 2020-08-19 through 2020-08-25 | five rows; every row `tradestatus=0`, `is_st=0`; `turn` and OHLCV were null | state fields required; `turn` and OHLCV are legal source nulls for this state |
| Early listed history | `000001.SZ`, 1991-04-03 through 1991-04-05 | three rows; every row `tradestatus=1`, `is_st=0` | state fields required and present |
| Delisting-boundary candidate | `600005.SH`, 2016-04-25 through 2016-04-29 | five rows; every row `tradestatus=1`, `is_st=0` | this probe alone is not proof of a delist date; lifecycle evidence remains authoritative |

## Contract

`baostock-trade-status-v1` requires `tradestatus` and `is_st` for each
applicable returned trading-day record. `turn` is not required when
`tradestatus=0`. A missing record remains `UNKNOWN`; it is never converted to
normal trading or non-ST. Securities before confirmed listing or after
confirmed delisting are `NOT_APPLICABLE`, while lifecycle uncertainty keeps the
denominator unknown rather than silently shrinking it.
