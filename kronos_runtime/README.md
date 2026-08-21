# Kronos Goal 1 Runtime

This directory is the standalone CUDA inference boundary for Kronos-base. The
main QuantRadar process does not import Torch.

## Setup (network allowed)

```bash
make kronos-runtime-setup
```

Setup creates `.venv-kronos`, checks out the exact upstream commit, downloads
the exact model and tokenizer revisions, and writes
`models/kronos/kronos_model_lock.json` with every runtime file SHA256.

## Verify and smoke (offline model access)

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv-kronos/bin/python kronos_runtime/model_lock.py verify --repo-root .
make kronos-gpu-smoke
```

The smoke command builds qfq inputs from the latest available real
`000300.SH` PIT snapshot, then runs the 1-stock, 50-stock, full eligible PIT
one-path, and full eligible PIT five-path benchmarks. It refuses CPU fallback,
another model, changed files, or a mutable revision. CUDA OOM may only reduce
the batch size.

Evidence is published to `reports/kronos/runtime_smoke/`. The marker
`KRONOS_BASE_GPU_RUNTIME_PASS` proves only the isolated runtime; it does not
open signal, formal backtest, or real-assist gates.
