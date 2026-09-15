# Audit batch 2: master and maintenance

Date: 2026-09-15

This receipt closes the second audit-remediation batch (F04--F06).  It records
the fixed release used for the check rather than inferring completion from a
queue count or a test result.

## Fixed-release result

The already archived BaoStock lifecycle observation and the read-only base
listing were regenerated into the canonical master, then published without an
upstream download:

| item | value |
| --- | --- |
| release | `R99a42307383acedd` |
| base commit | `0o6tgnmq5vabt3orqrk8rhqptniae26l` |
| supplemental commit | `7a4vrm1fkvp3cfeo4lnsdure5j6sgh75` |
| published SH/SZ lifecycle rows | 5,556 |
| listed rows at 2026-09-14 | 5,219 |
| delisted rows | 337 |
| BSE identity records | 343, explicitly outside the SH/SZ lifecycle table |

The fixed-release manifest reports 5,556 lifecycle rows.  `ReleaseReader` read
the same 5,556 rows, and the fixed-release Provider returned the same
point-in-time range.  `001220.XSHE`, whose listing date is 2026-02-03, was
present in `get_security_info(..., date="2026-09-14")`.  This verifies that the
published lifecycle master, research Provider and point-in-time filtering no
longer use separate mutable lists.

The status coordinator was not run for this receipt: doing so would make
unrelated upstream requests.  Its code path continues to label valuation and
industry stages `SKIPPED`, and status work remains governed by the persisted
queue, execution-time coverage audit and retry eligibility.

## Regression evidence

```
PYTHONPATH=backend .venv/bin/python -m pytest \
  tests/unit/test_datahub.py tests/unit/test_datahub_remediation.py -q
93 passed, 3 warnings
```

The warnings are upstream SQLAlchemy/FastAPI deprecations and did not affect
the DataHub assertions.

## Limitations retained

Lifecycle remains `PIT_PARTIAL`: the current BaoStock observation is evidence
of current lifecycle facts, not proof of historical public availability.
BSE identity remains a separate, explicit capability record; it does not claim
supported price or trade-status coverage.  This receipt does not change the
remaining status, valuation, market-cap, industry, adjustment or strict-PIT
coverage limitations.
