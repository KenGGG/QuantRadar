# Kronos Gate Correctness Design

## Scope

This change corrects four acceptance blockers in PR #2 without restoring the
old CSI300 PIT dependency for default Kronos signal research. The default
universe remains `all_a_liquid`; CSI PIT remains an independent optional
capability.

## Strict all-A PIT input eligibility

For `all_a_liquid`, a candidate must have a valid price row on the signal date.
The candidate query therefore selects A-share symbols whose `tradedate` equals
the signal date, not symbols that appeared at any earlier time. This excludes
delisted securities and securities without a signal-date price from the current
cross-section.

The shared market calendar defines the canonical input window: the 90 most
recent open market days ending at the signal date. A symbol is eligible only
when its returned price dates exactly equal that canonical sequence and its
OHLCVA values pass the existing completeness and structural checks. A provider
returning 90 older observations to fill a suspension gap is therefore rejected.

Signal-date enumeration for `all_a_liquid` clamps the requested end date to
`latest_price_date`. If no market dates remain after the clamp, it returns an
empty list. A direct input build also rejects a signal date later than the
latest available price date.

## Capability gates

`kronos_signal_research_ready` remains the permission to conduct OHLC-based
Kronos signal research. `research_backtest_ready` is added as the equivalent
research-only backtest permission.

`realistic_backtest_ready` may be true with fidelity `PARTIAL` when the latest
tradeability evidence is not blocked. It is not a formal-quality declaration.
`formal_backtest_ready` is true only when Kronos research is ready, latest
tradeability evidence is `PASS`, and corporate-action evidence is ready. While
any of those requirements are incomplete, it remains false. `real_assist_data_ready`
continues to require full latest tradeability evidence.

## Reproducible audit cache

The data-audit writer records the Dolt `data_commit` in `data_gate.json`. The
research pipeline reads a cached gate only if it is parseable and its
`data_commit` exactly matches the SignalRun's current Dolt HEAD. Missing,
malformed, or stale cache yields conservative false values for realistic,
formal, real-assist, and CSI PIT capabilities. The manifest records whether a
matched audit gate was used.

## CI isolation

Every test that opens a real `investment_data` connection carries the existing
`requires_dolt` marker, including the new all-A live test. The marker's
collection hook skips such tests when Dolt is unreachable, so GitHub Actions
runs pure unit tests without attempting `127.0.0.1:3307`.

## Testing and acceptance

Unit tests cover candidate exclusion for delisted or absent signal-date prices,
future-end clamping, a suspended/missing-date 90-day window, direct future
signal-date rejection, gate semantics, and matched versus stale/missing audit
caches. Live tests retain `requires_dolt` and skip in CI. Completion requires
the targeted Kronos unit suite, `make test`, frontend build, and green GitHub
Actions after pushing the branch.
