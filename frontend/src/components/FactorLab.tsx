import { useEffect, useState } from "react";
import { Alert, Button, Card, Input, Radio, Table } from "antd";
import { createFactorBatch, getFactorBatchSummary, getFactorCatalog, getIndexSnapshot, type FactorBatchSummary, type FactorCatalogRow } from "../api";

export function FactorLab() {
  const [rows, setRows] = useState<FactorCatalogRow[]>([]); const [error, setError] = useState(""); const [members, setMembers] = useState(""); const [release, setRelease] = useState(""); const [batch, setBatch] = useState(""); const [summary, setSummary] = useState<FactorBatchSummary | null>(null); const [poolType,setPoolType]=useState("CUSTOM_STATIC_POOL"); const [indexCode,setIndexCode]=useState("000300.SH"); const [snapshotDate,setSnapshotDate]=useState("2022-07-01");
  useEffect(() => { getFactorCatalog().then(r => setRows(r.factors)).catch(e => setError(String(e))); }, []);
  const ready = rows.filter(r => r.group === "price_volume");
  const start = async () => { try { let selected=members.split(/[\s,]+/).filter(Boolean); if(poolType!=="CUSTOM_STATIC_POOL") selected=(await getIndexSnapshot(indexCode,snapshotDate)).members; const r = await createFactorBatch({ release_id: release, members:selected, start_date: "2020-01-01", end_date: "2024-12-31", alpha_ids: ready.map(x => x.alpha_id), pool_type: poolType, snapshot_date: poolType==="CUSTOM_STATIC_POOL"?null:snapshotDate }); setBatch(r.experiment_id); } catch (e) { setError(String(e)); } };
  useEffect(() => { if (!batch) return; let alive=true; const poll=async()=>{ try { const r=await getFactorBatchSummary(batch); if(alive) setSummary(r); } catch(e){ if(alive)setError(String(e)); } }; void poll(); const timer=setInterval(poll,2000); return()=>{alive=false;clearInterval(timer)}; },[batch]);
  return <Card title="FactorLab" extra={<span>RAW 工程研究 · 非严格 PIT</span>}>
    {error && <Alert type="error" message={error} showIcon />}
    <p>共 {rows.length} 个 Alpha101 公式；默认可选择 {ready.length} 个量价项。输入 READY、完成计算与完成评价分别记录。</p>
    <Input placeholder="固定 release ID" value={release} onChange={e => setRelease(e.target.value)} style={{ marginBottom: 8 }} />
    <Radio.Group value={poolType} onChange={e=>setPoolType(e.target.value)} options={[{label:"自定义静态池",value:"CUSTOM_STATIC_POOL"},{label:"指数静态快照池（非 PIT）",value:"INDEX_SNAPSHOT_STATIC_POOL"}]} style={{marginBottom:8}} />
    {poolType==="CUSTOM_STATIC_POOL" ? <Input.TextArea placeholder="自定义静态股票池：以逗号或空格分隔代码，至少 20 只" value={members} onChange={e => setMembers(e.target.value)} rows={2} /> : <><Input value={indexCode} onChange={e=>setIndexCode(e.target.value)} placeholder="指数代码" /><Input value={snapshotDate} onChange={e=>setSnapshotDate(e.target.value)} placeholder="快照日期 YYYY-MM-DD" style={{marginTop:6}} /><Alert type="warning" showIcon message="静态指数快照池，不是历史 PIT 成分池" style={{marginTop:6}} /></>}
    <Button type="primary" onClick={start} disabled={!release || (poolType==="CUSTOM_STATIC_POOL" && members.split(/[\s,]+/).filter(Boolean).length < 20)} style={{ margin: "8px 0" }}>运行 82 个量价因子</Button>{batch && <span>批次：{batch}</span>}
    {summary && <Alert type={summary.status === "FAILED" ? "error" : "info"} showIcon message={`批次 ${summary.status}：${summary.completed}/${summary.requested}`} description={summary.error} style={{ marginBottom: 8 }} />}
    {summary && <Table size="small" pagination={{ pageSize: 8 }} rowKey="alpha_id" dataSource={summary.items} columns={[{title:"因子",dataIndex:"alpha_id"},{title:"计算",dataIndex:"calculation"},{title:"1日 IC",render:(_,r)=>r.evaluations?.["1"]?.summary?.ic_mean ?? "—"},{title:"5日 Rank IC",render:(_,r)=>r.evaluations?.["5"]?.summary?.rank_ic_mean ?? "—"},{title:"有效日期",render:(_,r)=>r.evaluations?.["1"]?.summary?.valid_dates ?? "—"}]} />}
    <Table size="small" pagination={{ pageSize: 12 }} rowKey="alpha_id" dataSource={rows} columns={[
      { title: "编号", dataIndex: "alpha_id" }, { title: "依赖组", dataIndex: "group" }, { title: "预热", dataIndex: "lookback_days" },
      { title: "输入资格", render: (_, r) => r.group === "price_volume" ? "READY" : "PARTIAL" }, { title: "评价", dataIndex: "evaluation_status" },
      { title: "公式", dataIndex: "formula", ellipsis: true },
    ]} />
  </Card>;
}
