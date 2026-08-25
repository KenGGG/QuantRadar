# QuantRadar Research MVP Design

## Goal

Build an isolated Research MVP that processes the preceding day's Enterprise Warning Center reports from the **热门研报**, **策略研究**, and **金融工程** channels into a full-text, traceable Feishu daily digest. It must not modify the existing backtest, Kronos runtime, or worker execution paths.

## Boundaries

- Use `(source, source_report_id)` as the immutable upstream report key.
- Use `publishDate`, `size`, and `from`; preserve `platform_order` and `snapshot_at`. Do not create a `hot_score`.
- Support PDFs only. Persist non-PDF metadata as `unsupported_content` and continue the run.
- Reuse the local MinerU HTTP API at `http://127.0.0.1:58000`, maximum concurrency one. QuantRadar owns a small client adapter and never imports OARadar at runtime.
- Implement only Agnes through a replaceable `ResearchLLMProvider` interface. Long reports must use deterministic chunks and a merge request; no tail truncation.
- Store raw PDFs and source Markdown outside Git in the configured local data root.
- Add read-only Research APIs and a compact verification page only. No reader, search workbench, rerun buttons, backtest bridge, or task queue framework.
- A daily task may be `READY`, `PARTIAL`, or `BLOCKED`; it must never present incomplete work as complete.

## Architecture

`research.pipeline.DailyResearchPipeline` orchestrates synchronous stages: collection, candidate selection, PDF download, MinerU parse, Agnes analysis, digest build, and outbox notification. Each stage records idempotent state in its own SQLAlchemy metadata registry. The CLI and systemd service invoke the pipeline outside FastAPI; FastAPI only queries the registry.

The QYJ collector opens an isolated persistent Chromium profile in headless mode and derives transient request headers from an authenticated page. It stores no credentials or headers in source control or logs. Authentication failures stop collection and publish diagnostic HTML/screenshot files only in the configured debug directory.

## Data contracts

Seven Research-owned tables are created independently: `research_reports`, `research_report_snapshots`, `research_artifacts`, `research_stage_runs`, `research_analyses`, `research_daily_digests`, and `research_outbox`. Their uniqueness contracts are respectively upstream report identity, per-date/channel snapshot, and notification key. Files use the configured `raw`, `source_md`, `analysis`, `digest`, `debug`, and `logs` directory layout.

Processing statuses are `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, and `UNSUPPORTED`; stage names are `DOWNLOAD`, `PARSE`, `ANALYZE`, and `VALIDATE`. PDF page counts come from a PDF-aware parser, while platform page counts are comparison metadata only.

## Analysis contracts

Market reports produce: `one_line_summary`, `core_points`, `key_facts`, `new_information`, `why_it_matters`, `companies`, `catalysts`, `risks`, `research_value`, and evidence. Quant reports produce: `research_question`, `economic_logic`, `data`, `universe`, `signal`, `method`, `rebalance`, `backtest_period`, `benchmark`, `cost`, `main_results`, `robustness`, `bias_risks`, `reproducibility`, `research_value`, `follow_up_questions`, and evidence.

Evidence always names an existing `chunk_id`; page bounds are optional and must not be invented. The validator checks referenced chunks and verifies cited numeric strings after normalization, recording `EVIDENCE_MISMATCH` rather than ignoring a mismatch.

## Delivery and acceptance

Candidate limits default to 10 hot, 20 strategy, 10 financial-engineering PDFs, with 30 unique reports per day. Digest coverage is first, followed by metadata trends, at most five hot highlights, and at most five strategy/quant highlights. Digest completeness is `READY` at 90% or greater, `PARTIAL` from 60% to 89%, and `BLOCKED` below 60%. Outbox keys are `research-digest:<date>:<digest_hash>` and Feishu keyword insertion is configured through `QUANTRADAR_FEISHU_REQUIRED_KEYWORD`.

Implementation completion is distinct from MVP pass. The latter requires 30 representative PDFs, three historical dates, and seven unattended daily runs after deployment.
