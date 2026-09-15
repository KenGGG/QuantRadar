# Audit batch 4: return semantics and execution entry points

Date: 2026-09-15

This receipt closes F10 and F14 without repeating the existing 1,615-session
low-Beta replay.  Neither change altered BulletTrade's matching, orders,
portfolio accounting, or a stored research result.

## Corporate-action boundary

`InvestmentDataProvider.get_split_dividend()` now has one explicit contract:
the selected stock release does not publish structured cash-dividend or
split-ratio terms, so the method raises `NotImplementedError`.  It cannot
convert a `preclose` gap into a cash event.  RAW price research therefore
remains price-path research; it does not claim total-return or account-level
eligibility.

## Shared backtest activation

`run_backtest()` and `run_unified_backtest()` now share
`activate_backtest_release()` for:

- fixed release activation;
- explicit-release missing failure (never a latest fallback);
- fallback only for legacy callers that supplied no release; and
- identical release, paired commits, schema and price-unit audit metadata.

The two entry points still intentionally differ only in their output adapters:
the synchronous API returns an in-memory snapshot, while the queued runner
writes BulletTrade's native report artifacts and its persisted run record.

## Regression evidence

```
PYTHONPATH=backend .venv/bin/python -m pytest \
  tests/unit/test_datahub_remediation.py -q
28 passed, 3 warnings
```

The test exercises shared activation with a fixed release and confirms an
explicit missing release raises instead of falling back.  It does not run a
historical replay.  The warnings are unrelated FastAPI and SQLAlchemy
deprecations.
