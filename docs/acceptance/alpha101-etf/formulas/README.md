# Alpha101 mathematical catalogue — research interpretation v1

This is a software formula catalogue, not qualification of historical market inputs,
statistical evaluation, an executable account or strict point-in-time availability.
All 101 rows remain `IMPLEMENTED_UNQUALIFIED`; the other three qualifications remain
`NOT_ASSESSED`. Group counts derived from expression fields are 82 price/volume,
1 historical market cap (#56), and 18 industry. No market endpoints or databases
were accessed by this task.

## Source and extraction

Primary source: Zura Kakushadze, [101 Formulaic Alphas, arXiv:1601.00991v3](https://arxiv.org/abs/1601.00991v3),
Appendix A, PDF pages 8–16. The source PDF identifies its manuscript date as
2015-12-09; arXiv identifies v3 as 2016-03-18. `provenance.json` records the downloaded
PDF SHA-256 and extraction method. `formulas.json` archives only the mathematical
expressions, with whitespace folded and standalone page numbers removed.
The runtime `_formulas.py` contains the same 101 strings. No third-party executable
implementation was copied. JSON/CSV dependency matrices are derived by the parser,
not a manually maintained field list.

## Interface and required inputs

```python
from quantradar.datahub.alpha101 import compute, dependency_matrix
rows = dependency_matrix()  # amount-based ADV interpretation
factor = compute(61, panel, adv_basis="amount")
```

Panel values are aligned, sorted, unique date × security pandas DataFrames. Named
fields follow the paper: `open/high/low/close/vwap/volume/amount/returns/cap` and
`indclass.sector/industry/subindustry`. Only fields actually used are required.
Missing fields or mismatched axes raise `ValueError`; nonfinite numerical inputs
become missing. Formula outputs retain the original axes. Nothing is filled,
backfilled, silently fetched or converted to a zero placeholder.

`volume` means shares, `amount` means currency amount, and `cap` means historical
**total** market capitalization. Adjustment, unit and total-market-cap evidence
must be audited before this API. It does not infer or repair these contracts.
`returns` is a supplied close-to-close research return, with a two-price-bar
primitive lookback. VWAP and all OHLC must have the same research adjustment basis.

`adv_basis="amount"` uses rolling mean of `amount`, matching the paper's amount
interpretation. `adv_basis="volume"` uses rolling mean of shares as a distinct
research version. The dependency matrix, result metadata and formula hashes
include the basis; there is no fallback between them.

An optional aligned **boolean** `panel["universe"]` supplies daily eligible members.
Missing eligibility is rejected. Rank, scale and industry neutralization use only
that day's explicitly eligible members. Any missing numerical input inside that
cross-section invalidates its result; missing industry labels also invalidate
neutralization for that date. Excluded members are missing in outputs. Primitive
time-series inputs outside the universe remain available for an entering member's
lookback. Without a universe mask every supplied column is an expected member.
The mask carries no claim of historical pool provenance: callers must audit it.

## Frozen conventions and source ambiguities

The complete `CONVENTIONS` object, `SEMANTICS_VERSION`, mathematical expression
and ADV basis enter the SHA-256 identity. These are documented interpretations,
not an assertion of bit-for-bit reproduction of proprietary original signals.

- `rank`: ascending cross-sectional average ties, ranks 1…N divided by N.
  `ts_rank`: the current observation's equivalent rank within its own complete
  single-security historical window. One member/one observation receives rank 1.
- Rolling windows include today, floor fractional lengths and require the whole
  window. Delay floors its nonnegative lag. Rolling lengths below 1 are rejected.
  Lookbacks compose along the tree: delay adds its lag, a rolling operation adds
  d−1, and branches take the maximum. The full initial warmup is masked even when
  a conditional could return a short-branch value sooner.
- Standard deviation and covariance use sample `ddof=1`. Correlation/covariance
  involving zero variance produce NaN. Valid zero covariance between nonconstant
  series remains zero. Standard deviation of constant observations itself is zero.
- `ts_argmin/max`: oldest position is 1, newest is d; an extremum tie chooses its
  oldest occurrence. The paper leaves index/tie conventions unspecified.
- Linear decay weights run 1…d from oldest to newest and sum to one.
- Division by zero, logarithms of nonpositive values, undefined powers and
  nonfinite results become NaN. Missing comparisons remain NaN, so they cannot
  silently select a ternary's false branch. A ternary uses the selected branch;
  missing data in its unselected branch does not substitute another value.
- The paper defines `signedpower(x,a)` as x^a. This version implements that literal
  operation, not the commonly used sign(x)·abs(x)^a variant. #1 squares a
  nonnegative chosen input and #84 raises a nonnegative time-series rank, so that
  distinction does not alter either catalogue formula's ordinary finite domain.
- The Appendix defines `min/max(x,d)` as rolling extrema but #71, #73, #76, #77,
  #82, #87, #88, #92 and #96 pass a panel as the second argument. This research
  interpretation freezes scalar second argument = rolling, panel second argument
  = elementwise. Those nine rows carry `panel_minmax_elementwise` explicitly.
  #29's `min(...,5)` remains a five-day rolling minimum. No claim is made that
  this overload is an explicit statement in the original Appendix.
- The paper omits several rank/variance/tie/missing-value implementation details;
  the rules above resolve them for this named research version. A separately
  audited industry mapping (for example a named A-share SW adaptation) is still
  required. One industry level is never substituted for another by this API.
- All results are t-close signals intended no earlier than t+1 execution. Paper
  delay-0 formulas #42/#48/#53/#54 carry `delay0_to_next_session`. This module
  returns signal rows; it does not itself shift them into an order or label series.

## Verification and coverage limits

`tests/unit/test_alpha101.py` includes independently worked #1/#6/#101 examples,
#61's 196-bar nested ADV/correlation boundary, a nested sum/delay example, tie and
zero-variance rules, industry levels, missing fields, mask transitions, parser
rejection and ADV version differentiation. All 101 formulas also run on synthetic
panels; appending future rows leaves old values unchanged. No synthetic result is
counted as real history coverage, independent market-source validation or account
return verification.

The maximum required history is **252 bars** (#48), rather than a flat 250-day
assumption. Other long examples include #19/#39 251, #52 241, #63 239, #32 235,
#71 225 and #37 201. Label horizons and execution dates must be added by callers.
Missing windows, constant rank histories and formula-specific invalid domains can
still yield NaNs after nominal warmup; `IMPLEMENTED_UNQUALIFIED` does not mean all
cells can or should be finite.
