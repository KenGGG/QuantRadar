# Low-Beta status dependency guard

The saved strategy `低 Beta 策略` (version 138) uses the full historical
CSI 300 universe and asks for `is_st` and `tradestatus` on each monthly
decision date.  A fixed-release preflight found that on `2024-01-02` all 300
members have no same-day status observation in `R12be9654e692afed`.

Before the fix, `get_extras(..., end_date=..., count=1)` could return an
older observation.  It now queries the as-of date exactly, so the result is
empty rather than stale.  Version 139 excludes a security when either
same-day status value is unknown.  Version **141 `低 Beta 策略 · 严格预检版`**
rejects the whole run if fewer than 20 securities have verified same-day
status; QuantRadar converts that strict rejection into a failed run rather
than an apparently successful zero-trade result.  These versions do not
change source version 138 or any historical run.

This is a research-mode guard: it exposes the unresolved `2023-06-10` onward
status coverage instead of manufacturing a complete backtest universe.  The
remaining strategy repair order remains pending until actual monthly
dependency dates and their required constituents have qualified status data.
