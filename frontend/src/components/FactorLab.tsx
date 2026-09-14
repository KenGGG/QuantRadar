import { useEffect, useState } from "react";
import { Alert, Button, Card, Input, Table } from "antd";
import { createFactorBatch, getFactorCatalog, type FactorCatalogRow } from "../api";

export function FactorLab() {
  const [rows, setRows] = useState<FactorCatalogRow[]>([]); const [error, setError] = useState(""); const [members, setMembers] = useState(""); const [release, setRelease] = useState(""); const [batch, setBatch] = useState("");
  useEffect(() => { getFactorCatalog().then(r => setRows(r.factors)).catch(e => setError(String(e))); }, []);
  const ready = rows.filter(r => r.group === "price_volume");
  const start = async () => { try { const r = await createFactorBatch({ release_id: release, members: members.split(/[\s,]+/).filter(Boolean), start_date: "2020-01-01", end_date: "2024-12-31", alpha_ids: ready.map(x => x.alpha_id), pool_type: "CUSTOM_STATIC_POOL" }); setBatch(r.experiment_id); } catch (e) { setError(String(e)); } };
  return <Card title="FactorLab" extra={<span>RAW 工程研究 · 非严格 PIT</span>}>
    {error && <Alert type="error" message={error} showIcon />}
    <p>共 {rows.length} 个 Alpha101 公式；默认可选择 {ready.length} 个量价项。输入 READY、完成计算与完成评价分别记录。</p>
    <Input placeholder="固定 release ID" value={release} onChange={e => setRelease(e.target.value)} style={{ marginBottom: 8 }} />
    <Input.TextArea placeholder="自定义静态股票池：以逗号或空格分隔代码，至少 20 只" value={members} onChange={e => setMembers(e.target.value)} rows={2} />
    <Button type="primary" onClick={start} disabled={!release || members.split(/[\s,]+/).filter(Boolean).length < 20} style={{ margin: "8px 0" }}>运行 82 个量价因子</Button>{batch && <span>批次：{batch}</span>}
    <Table size="small" pagination={{ pageSize: 12 }} rowKey="alpha_id" dataSource={rows} columns={[
      { title: "编号", dataIndex: "alpha_id" }, { title: "依赖组", dataIndex: "group" }, { title: "预热", dataIndex: "lookback_days" },
      { title: "输入资格", render: (_, r) => r.group === "price_volume" ? "READY" : "PARTIAL" }, { title: "评价", dataIndex: "evaluation_status" },
      { title: "公式", dataIndex: "formula", ellipsis: true },
    ]} />
  </Card>;
}
