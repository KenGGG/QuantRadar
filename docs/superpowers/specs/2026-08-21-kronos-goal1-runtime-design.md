# Kronos Goal 1 Runtime and GPU Smoke Design

## Scope

Goal 1 proves that the exact `Kronos-base` model can run reproducibly on this
machine's NVIDIA GPU. It does not generate research signals, portfolios, or
backtests. Goal 0 remains the data authority and its blocked research/trading
gates remain blocked.

## Immutable inputs

- Kronos source commit: `67b630e67f6a18c9e9be918d9b4337c960db1e9a`.
- Model: `NeoQuasar/Kronos-base` at immutable revision
  `2b554741eca47781b64468546e77fef3e85130e6`.
- Tokenizer: `NeoQuasar/Kronos-Tokenizer-base` at immutable revision
  `0e0117387f39004a9016484a186a908917e22426`.
- Maximum context: 512; smoke lookback: 90 trading days; forecast horizon: 10
  trading days.
- Fixed five-path seeds: `101, 211, 307, 401, 503`; temperature `0.6`, top-p
  `0.9`, top-k `0`, one sample per call.

The official upstream regression test pins the tokenizer revision above but
pins a `Kronos-small` model revision. It does not define a `Kronos-base`
regression revision. Goal 1 therefore uses the immutable current base-model
repository commit above and records this reason in the model lock.

## Isolation and offline boundary

`.venv-kronos` owns Torch and model dependencies; the main QuantRadar
environment never imports Torch. Setup is the only network-enabled operation:
it installs the exact dependency set, checks out the exact source commit, and
downloads exact Hugging Face snapshots. Normal lock verification and smoke
runs set Hugging Face offline flags and load only local snapshot paths.

QuantRadar creates a NumPy input package from the read-only
`InvestmentDataProvider`, then invokes `.venv-kronos/bin/python` through a
subprocess. The runtime rejects CPU, a non-base model, mutable revisions,
changed model files, a mismatched source commit, and CUDA unavailability. It
never falls back to another model or device. CUDA OOM may only reduce the batch
size and retry the same workload.

## Real input package

The benchmark date is the latest available `000300.SH` PIT snapshot, currently
2022-07-01. Candidates must be members at that snapshot, listed for at least
120 trading days, have exactly 90 complete qfq OHLCVA rows ending at the signal
date, have structurally valid OHLC, and be in the top 80 percent by recent
20-day average amount. Known ST, suspension, or tradeability state is applied
when available; absent state is recorded as PARTIAL rather than assumed normal.
Qfq uses `pre_factor_ref_date=signal_date`. Future timestamps come only from
the trading calendar; no future price is read.

The package contains arrays, symbols, timestamps, exclusions, the PIT snapshot
date, the Goal 0 data contract hash, and the Dolt commit. A manifest hash binds
all of these to the runtime output.

## Benchmark protocol and evidence

The model is loaded once and stages run in this order:

1. one eligible stock, one path;
2. first 50 deterministic eligible stocks, one path;
3. every eligible PIT stock, one path;
4. every eligible PIT stock, all five fixed paths.

Each stage records wall-clock runtime, peak allocated GPU memory, actual batch
size, symbols per second, output hashes, and errors. The one-stock fixed-seed
stage is repeated in the same process; exact output hashes must match. The
five-path stage preserves each path hash rather than only an average. A
backfill estimate is emitted only from measured full-universe performance and
an explicit count of covered PIT signal weeks; otherwise it is null with a
reason.

Artifacts are atomically published under `reports/kronos/runtime_smoke/`:

- `runtime_manifest.json`
- `runtime_gate.json`
- `benchmark.json`
- `determinism.json`
- `environment.json`
- `input_manifest.json`

`KRONOS_BASE_GPU_RUNTIME_PASS` is emitted only when source, dependency, model
hash, CUDA-only execution, all four benchmark stages, and fixed-seed
determinism pass. This marker is an isolated runtime result; it does not change
`signal_research_ready`, `formal_backtest_ready`, or
`real_assist_data_ready`.

## Testing

Unit tests cover immutable configuration, input eligibility, manifest hashing,
subprocess isolation, gate evaluation, deterministic report publication, and
failure behavior without importing Torch. CUDA integration tests use
`requires_kronos` and `requires_cuda` markers and run the real locked model.
Completion requires the Goal 1 unit suite, the real GPU smoke, artifact hash
validation, and the existing project regression checks with pre-existing
failures reported separately.
