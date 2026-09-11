# Low-Beta status dependency guard

The saved strategy `低 Beta 策略` (version 138) uses the full historical
CSI 300 universe and asks for `is_st` and `tradestatus` on each monthly
decision date.  A fixed-release preflight found that on `2024-01-02` all 300
members have no same-day status observation in `R12be9654e692afed`.

Before the fix, `get_extras(..., end_date=..., count=1)` could return an
older observation.  It now queries the as-of date exactly, so the result is
empty rather than stale.  A new immutable strategy version, **139 `低 Beta
策略 · 状态严格版`**, excludes a security when either same-day status value is
unknown.  It does not change source version 138 or any historical run.

This is a research-mode guard: it exposes the unresolved `2023-06-10` onward
status coverage instead of manufacturing a complete backtest universe.  The
remaining strategy repair order remains pending until actual monthly
dependency dates and their required constituents have qualified status data.
