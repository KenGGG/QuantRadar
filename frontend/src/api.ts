// QuantRadar WebUI API 客户端——只调用后端 /api/* 真实接口，绝不内置任何价格/回测逻辑。

export interface HealthResp {
  status: string;
  provider: string | null;
  environment?: Environment;
}

export type ResearchChannel = "HOT" | "STRATEGY" | "FINANCIAL_ENGINEERING";

export interface ResearchReport {
  id: number;
  title: string;
  institution: string | null;
  publish_date: string;
  content_type: string;
  channel: ResearchChannel;
  platform_order: number;
  status: string;
  pdf_status: string;
  mineru_status: string;
  agnes_status: string;
  research_value: string | null;
  reproducibility: string | null;
}

export interface ResearchOverview {
  date: string;
  metadata_count: number;
  pdf_success: number;
  pdf_failed: number;
  parse_success: number;
  parse_failed: number;
  analysis_success: number;
  analysis_failed: number;
  digest_status: string;
  outbox_status: string;
  sent_at: string | null;
  latest_operation_status: string;
  runtime_seconds: number | null;
  channels: Record<ResearchChannel, { count: number }>;
  observation: ResearchObservation;
}

export interface ResearchObservation { engineering_pass: boolean; live_pass: boolean; real_operating_days: number; required_operating_days: number; }
export interface ResearchDetail { id: number; basic: Record<string, unknown>; artifact: Record<string, unknown> | null; analysis: Record<string, unknown> | null; evidence: Array<Record<string, unknown>>; audit: Record<string, unknown> | null; }
export interface ResearchDigest { date: string; content_md: string; completeness: string; digest_hash: string; created_at: string; outbox: { status: string; attempt: number; sent_at: string | null; last_error: string | null } | null; }
export interface ResearchOperations { date: string; runs: Array<{ stage: string; status: string; attempt: number; started_at: string; finished_at: string | null; runtime_seconds: number | null }>; stages: Record<string, { success: number; failed: number; skipped: number }>; }

export interface PriceRow {
  date: string;
  [field: string]: string | number | null;
}

export interface PriceResp {
  security: string;
  rows: PriceRow[];
}

export interface Metric {
  final_total_value?: number | null;
  total_return?: number | null;
  max_drawdown?: number | null;
  days?: number | null;
  [k: string]: unknown;
}

export interface DailyRecord {
  date: string;
  total_value: number | null;
  cash?: number | null;
  positions_value?: number | null;
  returns?: number | null;
  returns_pct?: number | null;
}

export interface Trade {
  security: string | null;
  action: string | null;
  amount: number | null;
  price: number | null;
  value: number | null;
  commission?: number | null;
  time?: string | null;
}

export interface Position {
  security: string | null;
  amount: number | null;
  avg_cost?: number | null;
  price?: number | null;
  value?: number | null;
}

export interface Environment {
  provider: string;
  provider_version: string;
  dolt_commit: string | null;
  schema_hash: string | null;
  latest_data_date: string | null;
  bullettrade_commit: string;
  quantradar_commit: string;
}

export interface Snapshot {
  snapshot_id?: string;
  config_hash?: string;
  strategy_hash?: string;
  result_fingerprint?: string;
  result_hash?: string;
  metrics?: Metric;
  environment?: Environment;
  config?: Record<string, unknown>;
  data_asof?: string | null;
  records_count?: number;
  daily_records?: DailyRecord[];
  trades?: Trade[];
  positions?: Position[];
  [k: string]: unknown;
}

export interface BacktestSummary {
  strategy: string;
  security: string | null;
  start_date: string | null;
  end_date: string | null;
  initial_cash: number;
  frequency: string;
  records_count: number;
  trades_count: number;
  final_total_value: number | null;
}

export interface BacktestResp {
  summary: BacktestSummary;
  snapshot: Snapshot;
}

export interface BacktestPayload {
  security?: string;
  start_date?: string | null;
  end_date?: string | null;
  initial_cash?: number;
  frequency?: string;
  amount?: number;
  code?: string;
  benchmark?: string | null;
  fq?: string;
  strategy_name?: string;
  extras?: Record<string, unknown> | null;
}

export interface RunArtifact {
  name: string;
  size: number | null;
  ext: string;
  is_report: boolean;
}

export interface RunArtifactsResp {
  run_id: string;
  run_dir: string;
  artifacts: RunArtifact[];
  report_url: string;
  standard_report_url: string;
}

export interface RunRecord {
  run_id: string;
  strategy_id?: number | null;
  config?: Record<string, unknown> | null;
  status: string;
  error?: string | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  result_hash?: string | null;
  snapshot?: Snapshot | null;
  metrics?: Metric | null;
}

export interface RunSubmitResp {
  run_id: string;
  status: string;
  config?: Record<string, unknown>;
}

export interface ExperimentResp {
  name: string;
  kind?: string;
  config?: Record<string, unknown>;
  result_fingerprint?: string;
  metrics?: Metric;
  snapshot?: Snapshot;
  created_at?: string | null;
  [k: string]: unknown;
}

async function httpJson<T>(input: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(input, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`请求失败 ${resp.status}: ${text || resp.statusText}`);
  }
  return (await resp.json()) as T;
}

export function getHealth(): Promise<HealthResp> {
  return httpJson<HealthResp>("/api/health");
}

export function listResearchDates(): Promise<{ dates: string[] }> {
  return httpJson<{ dates: string[] }>("/api/research/dates");
}

export function listResearchReports(date: string, channel: ResearchChannel): Promise<{ reports: ResearchReport[] }> {
  const qs = new URLSearchParams({ date, channel });
  return httpJson<{ reports: ResearchReport[] }>(`/api/research/reports?${qs.toString()}`);
}

export function getResearchStatus(date: string): Promise<{ date: string; channels: Record<ResearchChannel, number> }> {
  return httpJson<{ date: string; channels: Record<ResearchChannel, number> }>(`/api/research/status?date=${encodeURIComponent(date)}`);
}

export function getResearchOverview(date: string): Promise<ResearchOverview> {
  return httpJson<ResearchOverview>(`/api/research/overview?date=${encodeURIComponent(date)}`);
}

export function getResearchReport(id: number): Promise<ResearchDetail> { return httpJson<ResearchDetail>(`/api/research/reports/${id}`); }
export function getResearchPdfUrl(id: number): string { return `/api/research/reports/${id}/pdf`; }
export function getResearchMarkdownUrl(id: number): string { return `/api/research/reports/${id}/markdown`; }
export function getResearchDigest(date: string): Promise<ResearchDigest> { return httpJson<ResearchDigest>(`/api/research/digests/${encodeURIComponent(date)}`); }
export function getResearchOperations(date: string): Promise<ResearchOperations> { return httpJson<ResearchOperations>(`/api/research/operations?date=${encodeURIComponent(date)}`); }
export function getResearchObservation(): Promise<ResearchObservation> { return httpJson<ResearchObservation>("/api/research/observation"); }

export function getPrice(params: {
  security: string;
  start_date?: string;
  end_date?: string;
  fq?: string;
  fields?: string;
  count?: number;
}): Promise<PriceResp> {
  const qs = new URLSearchParams();
  qs.set("security", params.security);
  if (params.start_date) qs.set("start_date", params.start_date);
  if (params.end_date) qs.set("end_date", params.end_date);
  if (params.fq) qs.set("fq", params.fq);
  if (params.fields) qs.set("fields", params.fields);
  if (params.count != null) qs.set("count", String(params.count));
  return httpJson<PriceResp>(`/api/price?${qs.toString()}`);
}

export interface PullResp {
  ok: boolean;
  returncode: number;
  message: string;
  environment?: Environment;
}

/** 在本地 Dolt 仓库执行 dolt pull 更新 investment_data。 */
export function pullData(): Promise<PullResp> {
  return httpJson<PullResp>("/api/data/pull", { method: "POST" });
}

export function runBacktest(payload: BacktestPayload): Promise<BacktestResp> {
  return httpJson<BacktestResp>("/api/backtest", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function runStrategy(payload: BacktestPayload): Promise<BacktestResp> {
  return httpJson<BacktestResp>("/api/backtest/strategy", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function submitAsync(payload: BacktestPayload): Promise<RunSubmitResp> {
  return httpJson<RunSubmitResp>("/api/backtest/async", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getRun(runId: string): Promise<RunRecord> {
  return httpJson<RunRecord>(`/api/backtest/runs/${encodeURIComponent(runId)}`);
}

export function getRunArtifacts(runId: string): Promise<RunArtifactsResp> {
  return httpJson<RunArtifactsResp>(`/api/backtest/runs/${encodeURIComponent(runId)}/artifacts`);
}

export function getRunReportUrl(runId: string, which: "full" | "standard" = "standard"): string {
  return `/api/backtest/runs/${encodeURIComponent(runId)}/report?which=${which}`;
}

/** 单次运行产物的单文件查看/下载地址（按扩展名推断 Content-Type）。 */
export function getRunArtifactUrl(runId: string, name: string): string {
  return `/api/backtest/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(name)}`;
}

export function listRuns(limit = 50): Promise<{ runs: RunRecord[] }> {
  return httpJson<{ runs: RunRecord[] }>(`/api/backtest/runs?limit=${limit}`);
}

export function listExperiments(): Promise<{ experiments: string[] }> {
  return httpJson<{ experiments: string[] }>("/api/experiments");
}

export function getExperiment(name: string): Promise<ExperimentResp> {
  return httpJson<ExperimentResp>(`/api/experiments/${encodeURIComponent(name)}`);
}

export function getSnapshotLoad(path: string): Promise<Snapshot> {
  const qs = new URLSearchParams();
  qs.set("path", path);
  return httpJson<Snapshot>(`/api/snapshot/load?${qs.toString()}`);
}
