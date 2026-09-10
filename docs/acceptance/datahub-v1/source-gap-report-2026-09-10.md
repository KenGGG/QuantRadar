# Source Gap Report — 2026-09-10

## `valuation_daily`

| Requirement | Tested source | Evidence | Result |
| --- | --- | --- | --- |
| Coverage reaches 2016-01 | Eastmoney via `akshare.stock_value_em` | 600519 and 000001 both begin 2018-01-02 | FAIL |
| Historical delisted security | Eastmoney via `akshare.stock_value_em` | 600005 raises `TypeError: 'NoneType' object is not subscriptable` | FAIL |
| `pe_ttm`, `pb_mrq`, `ps_ttm`, `pcf_ocf_ttm` | Same | All four returned for three non-delisted samples | PASS, insufficient |
| Historical date-slice | Eastmoney `RPT_VALUEANALYSIS_DET` | 2016-01-04 returns `code=9201`, `result=null` | FAIL |

Eastmoney is not qualified as the V1 canonical valuation source. No historical
or incremental backfill route is approved, and A0.2 was not run. A replacement
source requires a new user-approved Source Qualification Gate; no automatic
fallback is permitted.

## `security_lifecycle`

SSE list and delist endpoints passed their qualification sample, including
600005 in the delist set. Both SZSE endpoints failed with `SSLEOFError`, so the
required combined Shanghai/Shenzhen lifecycle source is not qualified. No
canonical lifecycle data is published.
