// QuantRadar WebUI API 客户端——只调用后端 /api/* 真实接口，绝不内置任何价格/回测逻辑。

export interface HealthResp {
  status: string;
  provider: string | null;
}

export interface PriceRow {
  date: string;
  [field: string]: string | number | null;
}

export interface PriceResp {
  security: string;
  rows: PriceRow[];
}

export interface BacktestSummary {
  security: string;
  start_date: string | null;
  end_date: string | null;
  initial_cash: number;
  frequency: string;
  records_count: number;
  final_total_value: number | null;
}

export interface Snapshot {
  result_fingerprint: string;
  asof: string;
  [key: string]: unknown;
}

export interface BacktestResp {
  summary: BacktestSummary;
  snapshot: Snapshot;
}

export interface BacktestPayload {
  security: string;
  start_date?: string | null;
  end_date?: string | null;
  initial_cash?: number;
  frequency?: string;
  amount?: number;
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

export function saveSnapshot(payload: {
  snapshot: Snapshot;
  name?: string;
}): Promise<{ path: string }> {
  return httpJson<{ path: string }>("/api/snapshot/save", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
