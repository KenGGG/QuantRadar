import { useEffect, useState } from "react";
import { Alert, Button, Card, Checkbox, DatePicker, Select, Spin, Table } from "antd";
import dayjs from "dayjs";
import { getETFTemplates, listDataHubReleases, preflightETF, type ETFTemplate, type ReleaseSummary } from "../api";

export function ETFResearch() {
  const [templates, setTemplates] = useState<ETFTemplate[]>([]); const [releases, setReleases] = useState<ReleaseSummary[]>([]);
  const [release, setRelease] = useState(""); const [selected, setSelected] = useState<string[]>(["equal_weight", "momentum", "trend", "inverse_vol", "erc"]);
  const [start, setStart] = useState("2021-01-04"); const [end, setEnd] = useState("2021-03-31");
  const [result, setResult] = useState<Array<{ template: string; blocked: boolean; missing: Array<Record<string, string>> }>>([]); const [error, setError] = useState(""); const [loading, setLoading] = useState(false);
  useEffect(() => { getETFTemplates().then(r => setTemplates(r.templates)).catch(e => setError(String(e))); listDataHubReleases().then(r => { setReleases(r.releases); setRelease(r.current_release_id); }).catch(e => setError(String(e))); }, []);
  const check = async () => { if (!release) return; setLoading(true); setError(""); try { setResult((await preflightETF({ release_id: release, start_date: start, end_date: end, templates: selected })).checks); } catch (e) { setError(String(e)); } finally { setLoading(false); } };
  return <Card title="ETF 研究" extra={<span>ETF_RAW · 不含完整权益收益还原</span>}>
    {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 12 }} />}
    <p>固定版本、固定 10 只 ETF 池；缺失观察只显示对实际模板调仓依赖的影响。</p>
    <Select value={release} onChange={setRelease} style={{ width: 370, marginRight: 8 }} options={releases.map(r => ({ value: r.release_id, label: `${r.release_id} · base ${r.base_commit.slice(0, 8)} · supp ${(r.supplemental_commit || "—").slice(0, 8)}` }))} />
    <DatePicker value={dayjs(start)} onChange={d => setStart(d?.format("YYYY-MM-DD") || "")} /><span> 至 </span><DatePicker value={dayjs(end)} onChange={d => setEnd(d?.format("YYYY-MM-DD") || "")} />
    <Checkbox.Group value={selected} onChange={v => setSelected(v as string[])} options={templates.map(t => ({ value: t.id, label: `${t.label} (${t.lookback} 日预热)` }))} style={{ display: "block", margin: "14px 0" }} />
    <Button type="primary" onClick={check} loading={loading} disabled={!release || !selected.length}>预检研究配置</Button>{loading && <Spin style={{ marginLeft: 8 }} />}
    <Table size="small" style={{ marginTop: 16 }} rowKey="template" pagination={false} dataSource={result} columns={[{ title: "模板", dataIndex: "template" }, { title: "状态", render: (_, r) => r.blocked ? "阻塞" : "可提交" }, { title: "缺失依赖", render: (_, r) => r.missing.length }]} />
  </Card>;
}
