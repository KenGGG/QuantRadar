# BaoStock recovery — limited P2 evidence

On 2026-09-11, a single BaoStock login and one day of `600519.SH` returned one
row successfully. A second independent, one-session sample read 2023-09-01 for
`600519.SH`, `300750.SZ`, and `688981.SH`; all three responses were archived in
the DataHub RawStore.

The controlled recovery did not produce `10001011`, did not retry, did not
rotate an address or account, and did not bulk backfill. The local evidence is:

- `/data/quantradar_data/baostock-recovery-probe.json`
- `/data/quantradar_data/baostock-qualification.json`

Each sampled response contains daily price, turnover, `tradestatus`, `isST`,
PE, PB, PS and `pcfNcfTTM`. The new bundle normalizer derives independent
price, status and valuation candidates from that one response. `pcfNcfTTM`
remains NCF and is not mapped to the approved OCF field.

The old base `bao_a_stock_eod_info` has no 2023-09-01 status row for these
samples. That is evidence of the previously identified tail gap, not grounds
to invent a normal/paused state. The recovery is sample-only: no historical
patch or valuation release has been published, and the 196+123 valuation
baseline is unchanged.
