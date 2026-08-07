// QuantRadar WebUI API 客户端——只调用后端 /api/* 真实接口，绝不内置任何价格/回测逻辑。

export interface HealthResp {
  status: string;
  provider: string | null;
  environment?: Environment;
}

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
  extras?: Record<string, unknown> | null;
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
