# DataHub V1 acceptance evidence

## Gate 0 — PASS

Read-only base audit used commit `dje7kjb4gb27khhfmqncnfhf00n9igcg`; the
complete SQL evidence is [base-audit.json](base-audit.json). No command wrote
to `/data/investment_data`.

| Fact | Observed result |
| --- | --- |
| Base price history | 18,437,822 rows, 1990-12-19 through 2026-09-08 |
| Existing reusable fields | `bao_a_stock_eod_info` has `turn`, `is_st`, `tradestatus`; 2016+ 6,911,355 rows / 5,095 symbols |
| Turn nulls | 176,571 of 176,628 null turns occur on 176,725 `tradestatus=0` paused rows; do not treat them as a generic missing value |
| Base lifecycle | `ts_a_stock_list` has 5,023 rows / 189 `delist_date` values, but ends 2022-07-18 and cannot be the V1 lifecycle source |
| Latest price cross-section | 5,554 symbols at 2026-09-08 |

The pinned implementation reference is `simonlin1212/a-stock-data`
`2012ce7cd0e75d379c5e6cbd3115514f300f3bc8`. It is an adapter reference only,
not a runtime dependency.

Three real source probes ran locally on 2026-09-09. Their raw responses are
kept outside Git under `data/runtime/datahub/gate0/`; their hashes and ranges
are recorded here so they remain reviewable without committing source payloads.

| Dataset / source | Observed coverage | PIT status and limitation |
| --- | --- | --- |
| `baostock_valuation_history` | 600519: 2,596 daily rows from 2016-01-04 to 2026-09-08; delisted 600005: 270 rows 2016-01-04 to 2017-02-14; 688981 begins 2020-07-16 | `PARTIAL`: query yields effective trade dates but no historic publication/available timestamp |
| `baostock_stock_basic` | 8,945 records; 5,553 SH/SZ A shares; 337 delisted; latest IPO 2026-09-07 | `PARTIAL`: present-day fetch cannot establish what was publicly known at a prior date |
| `sw_industry_history` | 1,164,800-byte XLS, SHA-256 `31e29a08c0c46ac05271fa82b484a0bb356cf3cc612f4abaea751157c34fc465`; 12,909 rows / 5,918 codes; effective dates 1990 through 2026-09-02 | `PARTIAL`: four rows have `update_date < effective_date`, so update date is not a valid publication date |

The source probe establishes interface availability only. It does not promise
full historical coverage. V1 coverage will be computed from the explicit
security pool, date range, and field, separating not-yet-listed, legal null,
source-not-covered, and acquisition-failed cases.

## Gate B — BaoStock client and endpoint diagnosis: PASS

`/data/quantradar_data` is now `ken:ken` mode `0750`, and an empty independent
supplemental Dolt repository is served at `127.0.0.1:3308` by the enabled
`quantradar-datahub-dolt.service` user service.

The former source failure was rechecked before treating it as permanent. The
isolated runtime is `/data/Projects/a-stock-research/QuantRadar/.venv/bin/python`
with official `baostock 0.9.3`. On 2026-09-09,
`public-api.baostock.com` resolved to `198.18.1.15`; both `nc` and Python
`socket.create_connection()` reached TCP/10030. A new `bs.login()` returned
`error_code=0`, and `query_history_k_data_plus` for `sh.600519`, 2026-09-01
through 2026-09-08, returned six daily rows including all four required
valuation fields. This rules out the current client-version and TCP-egress
failure modes. `www.baostock.com:10030` also accepted a diagnostic TCP
connection, but is not configured as a source endpoint because no official
fallback designation was found.

The prior `10002007` failure remains recorded in the durable journal as an
observed transient protocol failure. It did not write supplemental tables and
did not move `current_release`. Gate 1 may now proceed with the approved
`public-api.baostock.com` endpoint.

## Gate 1 current boundary

A real three-symbol validation backfill published `Rb60ab5f94b2a612b` and
proved the paired commit release path. A full-market backfill then completed
623 durable symbol units before its next recovery login received BaoStock
`10001011 黑名单用户，请与管理员联系`. The process was stopped immediately;
the journal has no published release and `current_release` remains
`Rb60ab5f94b2a612b`. No further BaoStock retries will run until the provider
removes the restriction. The V1 historical backfill and final acceptance are
therefore not complete.

## Gate A0 — BLOCKED

BaoStock is now suspended and its unpublished material is frozen. The approved
Eastmoney replacement was tested first with its required 2016-01-04 date slice:
`RPT_VALUEANALYSIS_DET`, filter `(TRADE_DATE='2016-01-04')`. The endpoint returned
`success=false`, code `9201`, message `返回数据为空`, and `result=null` after
one Governor-controlled retry. The rejected 89-byte raw response is stored by
SHA-256 `ea6528a2204b61a7ee34683a73ca00f8afdc86aadf3f765d4dae39bbfb19dbe7`;
the complete request and ledger evidence is
[eastmoney-a0-2026-09-09.json](eastmoney-a0-2026-09-09.json).

This fails the required 2016 valuation baseline before pagination, four-field
semantics, 600005 historical presence, or SSE/SZSE lifecycle coverage can be
evaluated. A0 stopped immediately: no other dates or sources were queried, no
backfill ran, and no Dolt commit or current release changed.
