# Audit batch 3: fixed-release research read

Date: 2026-09-15

This is a bounded read-only check of the research-input contract after the
lifecycle publication in `R99a42307383acedd`.  It did not create a FactorLab
batch, access holdout data, contact an upstream, or run a backtest.

## Fixed input sample

Twenty explicitly selected, non-delisted SH/SZ securities were read through
the release-bound Provider from 2020-07-29 through 2020-10-30.  The requested
research interval was 2020-09-01 through 2020-10-30.

| check | result |
| --- | --- |
| release | `R99a42307383acedd` |
| pool size | 20 explicit lifecycle members |
| lifecycle-universe cells | 1,240 |
| panel inputs | open, high, low, close, volume, amount, vwap, returns, cap, universe |
| Alpha #1 preflight | `READY` |
| Alpha #58 preflight | `BLOCKED_INPUT(indclass.sector)` |

The result proves that the Provider can read the current immutable lifecycle
release into the explicit universe mask, while a missing qualified industry
dictionary remains a data block.  It does not infer readiness from price
non-null values, and it does not represent full-market Alpha101 completion.

## Regression evidence

```
PYTHONPATH=backend .venv/bin/python -m pytest \
  tests/unit/test_datahub.py tests/unit/test_factorlab_evaluation.py -q
82 passed, 6 warnings
```

Warnings are external SQLAlchemy, FastAPI and Qlib deprecations.
