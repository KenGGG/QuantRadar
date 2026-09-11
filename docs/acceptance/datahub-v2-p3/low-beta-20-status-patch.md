# Low-Beta replay with 20 real status patches

`R12be9654e692afed` contains 23 BaoStock status records: the prior three
samples plus 20 stocks actually held by the low-Beta strategy on 2023-09-01.
The 20 rows were all absent from the base status table before collection. A
release-pinned `get_extras` replay returned all 20 `is_st=0` and
`tradestatus=1` values.

The original low-Beta strategy was replayed for 2023-09-01 through 2023-09-28
against this release. Its generated
`/tmp/quantradar-v2-status-replay/v2_lowbeta_patch/snapshot.json` records the
same result hash as the historical baseline:

`e24bd0d3d892ddc26c5aeafcd2b78c343e380432ebef251caa6aef1f8e07a745`.

This confirms that adding known-normal status for the actual first-day holdings
does not alter this particular run. The identity of the release, the raw
receipts, and the 20-row scope make the zero difference attributable rather
than an assumption that the data was ignored.
