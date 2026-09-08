import { useEffect, useState } from "react";
import { Alert, Button, Descriptions, Menu, Spin, Table, Tag } from "antd";
import { BarChartOutlined, FileTextOutlined, CodeOutlined, TableOutlined, FolderOutlined, AuditOutlined } from "@ant-design/icons";
import { getRun, getRunArtifacts, getRunArtifactUrl, getRunReportUrl, getRunReportData, type RunRecord, type RunArtifactsResp, type NativeReportData, type ReportTable } from "../api";
import { ReturnOverview } from "./ReturnOverview";

const sections = [
  { key: "overview", label: "收益概述", icon: <BarChartOutlined /> },
  { key: "trades", label: "交易详情", icon: <TableOutlined /> },
  { key: "positions", label: "每日持仓", icon: <TableOutlined /> },
  { key: "daily", label: "每日收益", icon: <BarChartOutlined /> },
  { key: "log", label: "日志输出", icon: <FileTextOutlined /> },
  { key: "source", label: "策略代码", icon: <CodeOutlined /> },
  { key: "full", label: "详细报告", icon: <BarChartOutlined /> },
  { key: "artifacts", label: "报告文件", icon: <FolderOutlined /> },
  { key: "audit", label: "配置与审计", icon: <AuditOutlined /> },
];
const columnNames: Record<string, string> = { date: "日期", code: "标的", amount: "持仓数量", closeable_amount: "可卖数量", avg_cost: "平均成本", acc_avg_cost: "累计成本", price: "价格", value: "持仓市值", floating_pnl: "浮动盈亏", floating_pnl_pct: "浮动盈亏 %", cash: "现金", positions_value: "持仓市值", total_value: "总资产", daily_positions_value: "当日持仓市值", daily_total_market_value: "当日总资产", daily_floating_pnl: "当日浮动盈亏", returns: "累计收益金额", returns_pct: "策略收益 %", benchmark_price: "基准价格", benchmark_value: "基准资产", benchmark_returns_pct: "基准收益 %", excess_returns_pct: "超额收益 %", daily_returns: "日收益率（小数）" };

function NativeTable({ data }: { data: ReportTable }) {
  if (!data.available) return <Alert type="info" showIcon message="本次原生报告未生成该明细文件，可在报告文件中核对产物。" />;
  return <Table className="native-table" size="small" rowKey={(_, index) => String(index)} dataSource={data.rows} scroll={{ x: "max-content" }}
    pagination={{ pageSize: 20, showSizeChanger: false, showTotal: total => `共 ${total} 条` }}
    columns={data.columns.map(key => ({ title: columnNames[key] || key, dataIndex: key, render: (v: string) => v === "" ? "—" : /^-?\d+(\.\d+)?$/.test(v) ? Number(v).toLocaleString("zh-CN", { maximumFractionDigits: key === "daily_returns" ? 6 : 2 }) : v }))} />;
}

export function ReportPage({ runId, onBack, onEdit }: { runId: string; onBack: () => void; onEdit: (run: RunRecord) => void }) {
  const [run, setRun] = useState<RunRecord | null>(null);
  const [arts, setArts] = useState<RunArtifactsResp | null>(null);
  const [data, setData] = useState<NativeReportData | null>(null);
  const [section, setSection] = useState("overview");
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const rec = await getRun(runId);
        if (!active) return;
        setRun(rec);
        const [files, result] = await Promise.allSettled([
          getRunArtifacts(runId),
          rec.status === "SUCCESS" ? getRunReportData(runId) : Promise.resolve(null),
        ]);
        if (!active) return;
        setError("");
        if (files.status === "fulfilled") setArts(files.value);
        else if (rec.status === "SUCCESS") setError(String(files.reason));
        if (result.status === "fulfilled") setData(result.value);
        else setError(String(result.reason));
      } catch (e) { if (active) setError(String(e)); }
      finally { if (active) setLoading(false); }
    };
    void refresh();
    const timer = setInterval(() => { if (!run || ["RUNNING", "PENDING"].includes(run.status)) void refresh(); }, 1500);
    return () => { active = false; clearInterval(timer); };
  }, [runId, run?.status]);

  useEffect(() => {
    if (section !== "log" && section !== "source") return;
    let active = true;
    setText("加载中…");
    fetch(getRunArtifactUrl(runId, section === "log" ? "backtest.log" : "strategy.py")).then(async r => {
      if (!r.ok) throw new Error(`文件读取失败 ${r.status}`);
      return r.text();
    }).then(t => { if (active) setText(t); }).catch(e => { if (active) setText(String(e)); });
    return () => { active = false; };
  }, [runId, section]);

  const cfg = run?.config || {};
  const env = run?.snapshot?.environment;
  return <div className="report-page">
    <div className="report-toolbar">
      <div><strong>{String(cfg.strategy_name || "回测报告")}</strong><span>设置：{String(cfg.start_date || "—")} 至 {String(cfg.end_date || "—")}， ¥ {Number(cfg.initial_cash || 0).toLocaleString()}，每天</span>
        <Tag color={run?.status === "SUCCESS" ? "success" : run?.status === "FAILED" ? "error" : "processing"}>{run?.status === "SUCCESS" ? "回测完成" : run?.status || "加载中"}</Tag></div>
      <div><Button onClick={onBack}>← 返回继续编辑</Button><Button type="primary" disabled={!run} onClick={() => run && onEdit(run)}>恢复源码与配置</Button></div>
    </div>
    <div className="report-workspace">
      <aside className="report-sidebar"><Menu mode="inline" selectedKeys={[section]} items={sections} onClick={e => setSection(e.key)} /><div className="report-sidebar-note">本地日频回测<br />{String(data?.meta.benchmark || cfg.benchmark || "无基准")}<br />复权：{String(cfg.fq || "none")}</div></aside>
      <section className="report-content">
        <div className="panel-heading">{sections.find(s => s.key === section)?.label}<span>{runId}</span></div>
        {loading && <div className="loading-pane"><Spin /></div>}
        {error && <Alert type="error" showIcon message="报告不可用" description={error} />}
        {run?.status === "FAILED" && <Alert type="error" showIcon message="回测失败" description={run.error} />}
        {run && ["RUNNING", "PENDING"].includes(run.status) && <Alert type="info" message="回测执行中，完成后自动加载报告" />}
        {section === "overview" && data && <ReturnOverview data={data} />}
        {(["trades", "positions", "daily"] as string[]).includes(section) && data && <NativeTable data={data[section as "trades" | "positions" | "daily"]} />}
        {(section === "log" || section === "source") && <pre className="report-console">{text}</pre>}
        {section === "full" && (arts?.artifacts.some(a => a.name === "report.html" && (a.size || 0) > 0)
          ? <iframe title="BulletTrade 回测报告" src={getRunReportUrl(runId, "full")} className="native-report-frame" />
          : !loading && <Alert type="info" message="详细报告文件暂不可用" />)}
        {section === "artifacts" && arts && <Table size="small" rowKey="name" pagination={false} dataSource={arts.artifacts} columns={[
          { title: "文件", dataIndex: "name", render: (name: string) => <a href={getRunArtifactUrl(runId, name)} download={name}>{name}</a> },
          { title: "类型", dataIndex: "ext" },
          { title: "大小", dataIndex: "size", render: (size: number) => `${(size / 1024).toFixed(1)} KB` },
        ]} />}
        {section === "audit" && run && <div className="audit-content"><Descriptions column={2} bordered size="small">
          {Object.entries({ "起始日期": cfg.start_date, "结束日期": cfg.end_date, "初始资金": cfg.initial_cash, "频率": cfg.frequency, "页面基准": cfg.benchmark, "实际基准": data?.meta.benchmark, "复权": cfg.fq, "数据源": env?.provider, "数据版本": env?.dolt_commit, "QuantRadar 版本": env?.quantradar_commit, "BulletTrade 版本": env?.bullettrade_commit, "策略哈希": run.snapshot?.strategy_hash, "配置哈希": run.snapshot?.config_hash, "结果哈希": run.result_hash }).map(([key, value]) => <Descriptions.Item key={key} label={key}>{String(value ?? "—")}</Descriptions.Item>)}
        </Descriptions></div>}
      </section>
    </div>
  </div>;
}
