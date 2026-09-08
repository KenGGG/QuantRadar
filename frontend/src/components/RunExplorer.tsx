import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Input, Select, Space, Table, Tag } from "antd";
import { listRuns, type RunRecord } from "../api";

export function RunExplorer({ onOpenReport, onEdit }: { onOpenReport: (runId: string) => void; onEdit: (run: RunRecord) => void }) {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const refresh = useCallback(async () => {
    setLoading(true);
    try { setRuns((await listRuns(100)).runs); setError(""); }
    catch (e) { setError(String(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const pending = runs.some(r => ["PENDING", "RUNNING"].includes(r.status));
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, [pending, refresh]);
  const filtered = runs.filter(r => (!status || r.status === status) && (`${r.config?.strategy_name || ""} ${r.run_id}`).toLowerCase().includes(query.toLowerCase()));
  return <div className="report-content">
    <div className="panel-heading">回测列表<span>最近 100 次运行</span></div>
    <div style={{ padding: 16 }}><Space wrap>
      <Input aria-label="搜索回测" placeholder="搜索策略名称或运行 ID" value={query} onChange={e => setQuery(e.target.value)} style={{ width: 260 }} allowClear />
      <Select aria-label="运行状态" value={status} onChange={setStatus} style={{ width: 130 }} options={[{ value: "", label: "全部状态" }, { value: "SUCCESS", label: "回测完成" }, { value: "FAILED", label: "回测失败" }, { value: "RUNNING", label: "执行中" }, { value: "PENDING", label: "排队中" }]} />
      <Button onClick={() => void refresh()} loading={loading}>刷新列表</Button>
    </Space></div>
    {error && <Alert type="error" showIcon message={error} />}
    <Table<RunRecord> size="small" rowKey="run_id" dataSource={filtered} loading={loading} scroll={{ x: 1000 }} pagination={{ pageSize: 15, showSizeChanger: false, showTotal: n => `共 ${n} 次回测` }}
      expandable={{ expandedRowRender: r => <div><div>运行 ID：{r.run_id}</div><div>结果哈希：{r.result_hash || "—"}</div>{r.error && <Alert type="error" message="回测失败" description={r.error} />}</div> }}
      columns={[
        { title: "策略名称", key: "name", render: (_, r) => <Button type="link" onClick={() => onOpenReport(r.run_id)}>{String(r.config?.strategy_name || r.config?.security || "未命名策略")}</Button> },
        { title: "回测区间", key: "range", render: (_, r) => `${r.config?.start_date || "—"} 至 ${r.config?.end_date || "—"}` },
        { title: "初始资金", key: "cash", render: (_, r) => Number(r.config?.initial_cash || 0).toLocaleString() },
        { title: "基准", key: "benchmark", render: (_, r) => String(r.config?.benchmark || "—") },
        { title: "复权", key: "fq", render: (_, r) => String(r.config?.fq || "none") },
        { title: "状态", dataIndex: "status", render: (s: string) => <Tag color={s === "SUCCESS" ? "success" : s === "FAILED" ? "error" : "processing"}>{s}</Tag> },
        { title: "操作", key: "actions", render: (_, r) => <Space><Button type="link" size="small" onClick={() => onOpenReport(r.run_id)}>查看报告</Button><Button type="link" size="small" onClick={() => onEdit(r)}>恢复源码与配置</Button></Space> },
      ]} />
  </div>;
}
