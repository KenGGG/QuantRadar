import { useEffect, useState } from "react";
import { Alert, Button, Card, Collapse, Descriptions, Drawer, Empty, Select, Space, Spin, Table, Tabs, Tag, Typography } from "antd";
import { getResearchDigest, getResearchMarkdownUrl, getResearchObservation, getResearchOperations, getResearchOverview, getResearchPdfUrl, getResearchReport, listResearchDates, listResearchReports, type ResearchChannel, type ResearchDetail, type ResearchDigest, type ResearchDigestChannel, type ResearchObservation, type ResearchOperations, type ResearchOverview, type ResearchReport } from "../api";
import { researchFieldLabel, researchStageLabel, researchStatusLabel, researchValueLabel } from "./researchLabels";

const CHANNELS: Array<{ key: ResearchChannel; label: string }> = [
  { key: "HOT", label: "热门研报" }, { key: "STRATEGY", label: "策略研究" }, { key: "FINANCIAL_ENGINEERING", label: "金融工程" },
];
const bodyTypeLabel = (value: ResearchReport["body_type"]) => ({ PDF: "PDF", WEIXIN: "微信", HTML: "HTML", MIXED: "混合", NO_CONTENT: "无可读正文" }[value]);
const stages = ["COLLECT", "DOWNLOAD/PREPARE", "PARSE", "ANALYZE", "DIGEST", "OUTBOX", "FEISHU"];

function statusTag(status?: string | null) {
  const value = status || "MISSING";
  const color = value === "SUCCESS" || value === "SENT" || value === "COMPLETE" ? "green" : value.startsWith("FAILED") ? "red" : value === "MISSING" ? "default" : "blue";
  return <Tag color={color}>{researchStatusLabel(value)}</Tag>;
}
function valueText(value: unknown, field?: string): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) return value.map((item) => valueText(item, field)).join("、");
  if (typeof value === "object") return JSON.stringify(Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, item]) => [researchFieldLabel(key), typeof item === "string" && key === "status" ? researchStatusLabel(item) : item])));
  return researchValueLabel(field, String(value));
}
function Markdown({ content }: { content: string }) { return <Typography.Paragraph style={{ whiteSpace: "pre-wrap", lineHeight: 1.8, marginBottom: 0 }}>{content}</Typography.Paragraph>; }
function DigestChannelCard({ item }: { item: ResearchDigestChannel }) {
  return <Card title={item.channel_label}>
    <Typography.Paragraph>昨日共采集 {item.article_count} 篇，成功分析 {item.analyzed_count} 篇，{item.failed_count} 篇待处理。</Typography.Paragraph>
    <Typography.Title level={5}>栏目概览</Typography.Title><Markdown content={item.overall_summary} />
    <Typography.Title level={5}>主要研究主题</Typography.Title>{item.major_themes.length ? <ol>{item.major_themes.map((theme) => <li key={theme}>{theme}</li>)}</ol> : <Typography.Text type="secondary">暂无成功分析文章。</Typography.Text>}
    <Typography.Title level={5}>重要观点与变化</Typography.Title><Markdown content={item.important_views} />
    <Typography.Title level={5}>文章索引</Typography.Title><Table<ResearchDigestChannel["article_index"][number]> size="small" rowKey={(article) => `${item.channel}-${article.report_id}`} pagination={false} dataSource={item.article_index} columns={[
      { title: "序号", dataIndex: "platform_order", width: 70 }, { title: "标题", dataIndex: "title" }, { title: "机构", dataIndex: "institution", render: (value) => valueText(value) },
      { title: "一句话", dataIndex: "one_line_summary" }, { title: "核心观点", dataIndex: "core_conclusion" }, { title: "主要方法/逻辑", dataIndex: "method_or_logic" },
    ]} />
  </Card>;
}

export function ResearchMVP() {
  const [dates, setDates] = useState<string[]>([]);
  const [date, setDate] = useState<string>();
  const [channel, setChannel] = useState<ResearchChannel>("HOT");
  const [reports, setReports] = useState<ResearchReport[]>([]);
  const [overview, setOverview] = useState<ResearchOverview>();
  const [digest, setDigest] = useState<ResearchDigest>();
  const [operations, setOperations] = useState<ResearchOperations>();
  const [observation, setObservation] = useState<ResearchObservation>();
  const [detail, setDetail] = useState<ResearchDetail>();
  const [open, setOpen] = useState(false);
  const [artifact, setArtifact] = useState<"pdf" | "markdown">();
  const [markdown, setMarkdown] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  useEffect(() => {
    listResearchDates().then((result) => { setDates(result.dates); setDate(result.dates[0]); })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法读取采集记录"))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    if (!date) return;
    setLoading(true); setError(undefined);
    Promise.all([listResearchReports(date, channel), getResearchOverview(date), getResearchOperations(date), getResearchObservation()])
      .then(([list, nextOverview, nextOperations, nextObservation]) => { setReports(list.reports); setOverview(nextOverview); setOperations(nextOperations); setObservation(nextObservation); })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法读取研报存储"))
      .finally(() => setLoading(false));
    getResearchDigest(date).then(setDigest).catch(() => setDigest(undefined));
  }, [date, channel]);

  const showDetail = (report: ResearchReport) => {
    setOpen(true); setDetail(undefined); setArtifact(undefined); setMarkdown(undefined);
    getResearchReport(report.id).then(setDetail).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法读取报告详情"));
  };
  const showMarkdown = async () => {
    if (!detail) return;
    setArtifact("markdown");
    try { setMarkdown(await (await fetch(getResearchMarkdownUrl(detail.id))).text()); } catch { setMarkdown("Markdown 文件暂不可用。"); }
  };

  const overviewBody = <Space direction="vertical" style={{ width: "100%" }}>
    <Card><Descriptions size="small" column={{ xs: 1, sm: 2, md: 4 }} items={[
      ["元数据数量", overview?.metadata_count], ["PDF", `${overview?.pdf_success ?? 0} 成功 / ${overview?.pdf_failed ?? 0} 失败`], ["MinerU", `${overview?.parse_success ?? 0} 成功 / ${overview?.parse_failed ?? 0} 失败`], ["Agnes", `${overview?.analysis_success ?? 0} 成功 / ${overview?.analysis_failed ?? 0} 失败`],
      ["每日摘要", overview?.digest_status ? statusTag(overview.digest_status) : "—"], ["发件箱", overview?.outbox_status ? statusTag(overview.outbox_status) : "—"], ["发送时间", overview?.sent_at], ["最近运行", overview?.latest_operation_status ? statusTag(overview.latest_operation_status) : "—"], ["运行秒数", overview?.runtime_seconds],
    ].map(([label, content]) => ({ key: String(label), label: String(label), children: typeof content === "object" ? content : valueText(content) }))} /></Card>
    <Card title="7 日真实运行观察"><Space wrap><Tag color={observation?.engineering_pass ? "green" : "red"}>REPORT_MVP_ENGINEERING_PASS = {String(observation?.engineering_pass)}</Tag><Tag color="blue">REPORT_MVP_7D_LIVE_PASS = false</Tag><Typography.Text>{observation?.real_operating_days ?? 0} / {observation?.required_operating_days ?? 7} 个真实运行日</Typography.Text></Space></Card>
    <Card title="栏目概览"><Space wrap>{CHANNELS.map((item) => <Tag key={item.key}>{item.label}：{overview?.channels[item.key]?.count ?? 0} 篇</Tag>)}</Space></Card>
  </Space>;

  const reportsBody = <Space direction="vertical" style={{ width: "100%" }}>
    <Select style={{ width: 150 }} value={channel} options={CHANNELS.map((item) => ({ value: item.key, label: item.label }))} onChange={(next) => setChannel(next as ResearchChannel)} />
    <Table<ResearchReport> rowKey="id" pagination={{ pageSize: 20, showSizeChanger: false }} dataSource={reports} columns={[
      { title: "序号", dataIndex: "platform_order", width: 70 },
      { title: "标题", dataIndex: "title", render: (item, report) => <Typography.Link onClick={() => showDetail(report)}>{item}</Typography.Link> },
      { title: "机构", dataIndex: "institution", width: 130, render: (item) => valueText(item) }, { title: "栏目", dataIndex: "channel", width: 110, render: (item) => CHANNELS.find((channelItem) => channelItem.key === item)?.label || item },
      { title: "正文类型", dataIndex: "body_type", width: 100, render: (item) => bodyTypeLabel(item as ResearchReport["body_type"]) },
      { title: "Source", dataIndex: "pdf_status", width: 90, render: statusTag }, { title: "解析", dataIndex: "mineru_status", width: 95, render: statusTag }, { title: "Agnes", dataIndex: "agnes_status", width: 95, render: statusTag },
      { title: "研究价值", dataIndex: "research_value", width: 100, render: (item) => valueText(item, "research_value") }, { title: "可复现性", dataIndex: "reproducibility", width: 100, render: (item) => valueText(item, "reproducibility") },
      { title: "操作", width: 70, render: (_, report) => <Button type="link" onClick={() => showDetail(report)}>查看</Button> },
    ]} />
  </Space>;

  const digestBody = digest ? <Space direction="vertical" style={{ width: "100%" }}>
    <Card><Descriptions size="small" column={2} items={[
      { key: "completeness", label: "完整性", children: statusTag(digest.completeness) }, { key: "hash", label: "日报哈希", children: digest.digest_hash }, { key: "created", label: "创建时间", children: digest.created_at },
      { key: "outbox", label: "发件箱", children: digest.outbox ? statusTag(digest.outbox.status) : "—" }, { key: "sent", label: "发送时间", children: digest.outbox?.sent_at || "—" }, { key: "error", label: "最近错误", children: digest.outbox?.last_error || "—" },
    ]} /></Card>{digest.content?.channels?.map((item) => <DigestChannelCard key={item.channel} item={item} />)}
    {digest.content?.processing_exceptions?.length ? <Card title="处理异常"><Table size="small" pagination={false} rowKey={(item) => `${item.channel}-${item.title}`} dataSource={digest.content.processing_exceptions} columns={[
      { title: "标题", dataIndex: "title" }, { title: "所属栏目", dataIndex: "channel", render: (item) => CHANNELS.find((channelItem) => channelItem.key === item)?.label || item }, { title: "失败阶段", dataIndex: "stage", render: researchStageLabel }, { title: "失败原因", dataIndex: "reason" },
    ]} /></Card> : null}<Card title="每日摘要（原文）"><Markdown content={digest.content_md} /></Card>
  </Space> : <Empty description="该日期尚无每日摘要" />;

  const operationBody = <Space direction="vertical" style={{ width: "100%" }}>
    <Card title="阶段统计"><Table size="small" pagination={false} rowKey="stage" dataSource={stages.map((stage) => ({ stage, ...(operations?.stages[stage] || { success: 0, failed: 0, skipped: 0 }) }))} columns={[{ title: "阶段", dataIndex: "stage", render: researchStageLabel }, { title: "成功", dataIndex: "success" }, { title: "失败", dataIndex: "failed" }, { title: "跳过", dataIndex: "skipped" }]} /></Card>
    <Card title="最近运行"><Table<ResearchOperations["runs"][number]> size="small" rowKey={(item) => `${item.stage}-${item.started_at}-${item.attempt}`} pagination={{ pageSize: 10 }} dataSource={operations?.runs || []} columns={[{ title: "阶段", dataIndex: "stage", render: researchStageLabel }, { title: "状态", dataIndex: "status", render: statusTag }, { title: "开始时间", dataIndex: "started_at" }, { title: "结束时间", dataIndex: "finished_at", render: (item) => valueText(item) }, { title: "运行秒数", dataIndex: "runtime_seconds", render: (item) => valueText(item) }]} /></Card>
    <Card title="最近 7 个真实运行日"><Table size="small" pagination={false} dataSource={[]} locale={{ emptyText: "观察期尚未开始；历史回放不会计入。" }} columns={[{ title: "日期", dataIndex: "date" }, { title: "采集", dataIndex: "collect" }, { title: "PDF", dataIndex: "pdf" }, { title: "解析", dataIndex: "parse" }, { title: "分析", dataIndex: "analysis" }, { title: "每日摘要", dataIndex: "digest" }, { title: "飞书", dataIndex: "feishu" }, { title: "状态", dataIndex: "status" }]} /></Card>
  </Space>;

  return <Space direction="vertical" size="large" style={{ width: "100%" }}>
    <div><Typography.Title level={3} style={{ marginBottom: 4 }}>研报</Typography.Title><Typography.Text type="secondary">只读展示已持久化的企业预警研报结果。</Typography.Text></div>
    {error && <Alert type="warning" showIcon message="研报存储暂不可用" description={error} />}
    <Card size="small"><Space wrap><Typography.Text>采集日期</Typography.Text><Select style={{ minWidth: 150 }} value={date} placeholder="暂无已采集日期" options={dates.map((item) => ({ value: item, label: item }))} onChange={setDate} />{CHANNELS.map((item) => <Tag key={item.key}>{item.label} {overview?.channels[item.key]?.count ?? 0} 篇</Tag>)}</Space></Card>
    {loading && !overview ? <div style={{ textAlign: "center", padding: 36 }}><Spin /></div> : <Tabs items={[{ key: "overview", label: "今日概览", children: date ? overviewBody : <Empty /> }, { key: "reports", label: "研报列表", children: reportsBody }, { key: "digest", label: "每日摘要", children: digestBody }, { key: "operations", label: "运行状态", children: operationBody }]} />}
    <Drawer title="研报详情（只读）" width={760} open={open} onClose={() => setOpen(false)}>{!detail ? <Spin /> : <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Card title="基本信息"><Descriptions size="small" column={2} items={Object.entries(detail.basic).map(([key, item]) => ({ key, label: researchFieldLabel(key), children: valueText(item, key) }))} /></Card>
      <Card title="文件产物"><Descriptions size="small" column={2} items={Object.entries(detail.artifact || {}).filter(([key]) => !key.startsWith("has_")).map(([key, item]) => ({ key, label: researchFieldLabel(key), children: valueText(item, key) }))} /><Space style={{ marginTop: 12 }}>{detail.artifact?.has_pdf === true && <Button onClick={() => setArtifact("pdf")}>查看 PDF</Button>}{detail.artifact?.has_markdown === true && <Button onClick={showMarkdown}>查看 Markdown</Button>}</Space>{artifact === "pdf" && <iframe title="研报 PDF" src={getResearchPdfUrl(detail.id)} style={{ width: "100%", height: 500, border: 0, marginTop: 12 }} />}{artifact === "markdown" && <Card size="small" style={{ marginTop: 12 }}><Markdown content={markdown || "加载中…"} /></Card>}</Card>
      <Card title="Agnes 分析"><Descriptions size="small" column={1} items={Object.entries(detail.analysis || {}).map(([key, item]) => ({ key, label: researchFieldLabel(key), children: key === "status" ? statusTag(String(item)) : valueText(item, key) }))} /></Card>
      <Card title="证据"><Collapse items={detail.evidence.map((item) => ({ key: String(item.chunk_id), label: `分块 ${item.chunk_id} · #${item.chunk_index} · 位置 ${item.source_start}-${item.source_end}`, children: <><Typography.Text type="secondary">SHA-256：{valueText(item.chunk_sha256)}</Typography.Text><Markdown content={valueText(item.text)} /></> }))} /></Card>
      <Card title="审计信息"><Descriptions size="small" column={1} items={Object.entries(detail.audit || {}).map(([key, item]) => ({ key, label: researchFieldLabel(key), children: valueText(item, key) }))} /></Card>
    </Space>}</Drawer>
  </Space>;
}
