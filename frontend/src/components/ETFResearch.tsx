import { useEffect, useState } from "react";
import { Alert, Button, Card, Checkbox, DatePicker, Select, Spin, Table } from "antd";
import dayjs from "dayjs";
import { createETFExperiment, getETFExperiment, getETFTemplates, getIndustryETFPool, getRunReportUrl, listDataHubReleases, preflightETF, type ETFGroup, type IndustryETFCategory, type ETFTemplate, type ReleaseSummary } from "../api";

export function ETFResearch() {
  const [templates, setTemplates] = useState<ETFTemplate[]>([]); const [releases, setReleases] = useState<ReleaseSummary[]>([]);
  const [release, setRelease] = useState(""); const [selected, setSelected] = useState<string[]>(["equal_weight", "momentum", "trend", "inverse_vol", "erc"]);
  const [start, setStart] = useState("2021-01-04"); const [end, setEnd] = useState("2021-03-31");
  const [result, setResult] = useState<Array<{ template: string; blocked: boolean; missing: Array<Record<string, string>> }>>([]); const [group, setGroup] = useState<ETFGroup | null>(null); const [industry, setIndustry] = useState<Record<string, IndustryETFCategory>>({}); const [error, setError] = useState(""); const [loading, setLoading] = useState(false);
  useEffect(() => { getETFTemplates().then(r => setTemplates(r.templates)).catch(e => setError(String(e))); listDataHubReleases().then(r => { setReleases(r.releases); setRelease(r.current_release_id); }).catch(e => setError(String(e))); }, []);
  useEffect(() => { if (release) getIndustryETFPool(release).then(r => setIndustry(r.categories)).catch(e => setError(String(e))); }, [release]);
  const check = async () => { if (!release) return; setLoading(true); setError(""); try { setResult((await preflightETF({ release_id: release, start_date: start, end_date: end, templates: selected })).checks); } catch (e) { setError(String(e)); } finally { setLoading(false); } };
  const run = async () => { if (!release) return; setLoading(true); setError(""); try { const created = await createETFExperiment({ release_id: release, start_date: start, end_date: end, templates: selected }); setGroup(created); const items = (created.config?.["items"] ?? []) as Array<{ template: string; status: string; preflight?: { missing?: Array<Record<string, string>> } }>; setResult(items.map(i => ({ template: i.template, blocked: i.status === "PRECHECK_BLOCKED", missing: i.preflight?.missing || [] }))); } catch (e) { setError(String(e)); } finally { setLoading(false); } };
  useEffect(() => { if (!group?.experiment_id) return; let alive=true; const poll=async()=>{try { const current=await getETFExperiment(group.experiment_id); if(alive)setGroup(current); }catch(e){if(alive)setError(String(e));}}; void poll(); const timer=setInterval(poll,2000); return()=>{alive=false;clearInterval(timer)}; },[group?.experiment_id]);
  return <Card title="ETF 研究" extra={<span>ETF_RAW · 不含完整权益收益还原</span>}>
    {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 12 }} />}
    <p>固定版本、固定 10 只 ETF 池；缺失观察只显示对实际模板调仓依赖的影响。</p>
    <Select value={release} onChange={setRelease} style={{ width: 370, marginRight: 8 }} options={releases.map(r => ({ value: r.release_id, label: `${r.release_id} · base ${r.base_commit.slice(0, 8)} · supp ${(r.supplemental_commit || "—").slice(0, 8)}` }))} />
    <DatePicker value={dayjs(start)} onChange={d => setStart(d?.format("YYYY-MM-DD") || "")} /><span> 至 </span><DatePicker value={dayjs(end)} onChange={d => setEnd(d?.format("YYYY-MM-DD") || "")} />
    <Checkbox.Group value={selected} onChange={v => setSelected(v as string[])} options={templates.map(t => ({ value: t.id, label: `${t.label} (${t.lookback} 日预热)` }))} style={{ display: "block", margin: "14px 0" }} />
    <Button type="primary" onClick={check} loading={loading} disabled={!release || !selected.length}>预检研究配置</Button><Button onClick={run} loading={loading} disabled={!release || !selected.length} style={{ marginLeft: 8 }}>串行运行实验组</Button>{loading && <Spin style={{ marginLeft: 8 }} />}
    <Table size="small" style={{ marginTop: 16 }} rowKey="template" pagination={false} dataSource={result} columns={[{ title: "模板", dataIndex: "template" }, { title: "状态", render: (_, r) => r.blocked ? "阻塞" : "可提交" }, { title: "缺失依赖", render: (_, r) => r.missing.length }]} />
    <Card size="small" title="五类行业 ETF（身份先于收益）" style={{marginTop:12}}><Table size="small" pagination={false} rowKey="label" dataSource={Object.entries(industry).map(([key,row])=>({key,...row}))} columns={[{title:"类别",dataIndex:"label"},{title:"冻结定义",dataIndex:"definition"},{title:"资格",dataIndex:"status"},{title:"入选 ETF",render:(_,r)=>r.selected?.symbol || "—"},{title:"原因",dataIndex:"reason"}]} /></Card>
    {group && <Card size="small" title={`实验组 ${group.experiment_id}`} style={{marginTop:12}}><p>固定版本：{String(group.config?.release_id || "—")} · base {String(group.config?.base_commit || "—").slice(0,8)} · supplemental {String(group.config?.supplemental_commit || "—").slice(0,8)}</p>
      <Table size="small" rowKey="template" pagination={false} dataSource={group.config?.items || []} columns={[{title:"模板",dataIndex:"template"},{title:"状态",dataIndex:"status"},{title:"运行",render:(_,r)=>r.run_id?<a href={getRunReportUrl(r.run_id)} target="_blank" rel="noreferrer">{r.run_id}</a>:"—"},{title:"原因",dataIndex:"error"}]} />
    </Card>}
  </Card>;
}
