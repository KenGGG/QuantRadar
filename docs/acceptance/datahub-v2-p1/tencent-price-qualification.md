# Tencent daily-price qualification — limited P1 evidence

The local adapter is `akshare.stock_zh_a_hist_tx@1.18.94`. Its implementation
uses Tencent's `proxy.finance.qq.com` endpoint and iterates by year, so the
request ledger treats each year as a separate network attempt.

Four unadjusted responses were archived in the existing RawStore and compared
with the pinned base commit `uhdpedb4pr97ve80aq6nrabr66atsqtq` on 2023-09-01:

| Sample | Security class | Result |
| --- | --- | --- |
| `sh600519` | Main board | PASS |
| `sz300750` | ChiNext | PASS |
| `sh688981` | STAR Market | PASS |
| `sh000300` | Index | PASS |

All OHLC values match within 0.01 yuan. Amount matches after the base table's
thousand-yuan to yuan conversion. Main-board and ChiNext volume matches after
hands to shares conversion with an explicit tolerance of at most 100 shares:
Tencent rounds that representation. STAR volume and the sampled CSI 300 index
volume are already shares. The latter exposed and fixed an incorrect universal
index volume multiplier in the provider.

The machine-readable, pinned evidence is
`/data/quantradar_data/akshare-tencent-qualification.json`; it includes raw
SHA-256 receipts, adapter version, fields, comparisons, and tolerances.

This establishes only a sampled field/unit contract. It does not establish
complete historical availability, point-in-time availability, a universal
index rule, or permission to overwrite `final` data. No Tencent patch has been
published.
