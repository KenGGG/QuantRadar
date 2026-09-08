import { useEffect, useState } from "react";
import { Button, Menu, Spin } from "antd";
import { BarChartOutlined, CodeOutlined, HistoryOutlined } from "@ant-design/icons";
import { getHealth, type RunRecord, type HealthResp } from "./api";
import { DataStatus } from "./components/DataStatus";
import { StrategyWorkbench } from "./components/StrategyWorkbench";
import { RunExplorer } from "./components/RunExplorer";
import { ExperimentCompare } from "./components/ExperimentCompare";
import { ReportPage } from "./components/ReportPage";
import { ResearchMVP } from "./components/ResearchMVP";

type TabKey = "data" | "research" | "strategy" | "runs" | "experiments";
const labels = { strategy: "策略回测", runs: "运行记录", data: "数据状态", research: "研报", experiments: "实验对比" };

export function App() {
  const [health, setHealth] = useState<HealthResp | null>(null);
  const [tab, setTab] = useState<TabKey>("strategy");
  const [loading, setLoading] = useState(true);
  const [viewRunId, setViewRunId] = useState<string | null>(null);
  const [lastRunId, setLastRunId] = useState<string | null>(null);
  const [name, setName] = useState("买入持有");
  const [restoreRun, setRestoreRun] = useState<RunRecord | null>(null);
  const navigate = (key: TabKey) => { setViewRunId(null); setTab(key); };
  const editRun = (run: RunRecord) => { setRestoreRun({ ...run }); navigate("strategy"); };
  const openReport = (runId: string) => { setLastRunId(runId); setViewRunId(runId); setTab("strategy"); };
  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null)).finally(() => setLoading(false));
  }, []);

  return <div className="app-shell">
    <header className="global-header">
      <a className="app-logo" href="#" onClick={e => { e.preventDefault(); navigate("strategy"); }}><span className="logo-bars"><i /><i /><i /></span>QuantRadar</a>
      <Menu theme="dark" mode="horizontal" selectedKeys={[tab]} onClick={e => navigate(e.key as TabKey)}
        items={Object.entries(labels).map(([key, label]) => ({ key, label }))} />
      <span className="connection" title={health?.provider || "未连接"}><i className={health ? "online" : "offline"} />本地研究</span>
    </header>
    <div className="workspace-header">
      <div className="workspace-title"><CodeOutlined /><span>{viewRunId ? "回测详情" : tab === "strategy" ? name : labels[tab]}</span><small>{tab === "strategy" ? "Python3 · 日频" : "QuantRadar 研究平台"}</small></div>
      {(tab === "strategy" || tab === "runs") ? <nav className="workspace-tabs" aria-label="策略工作区">
        <button className={tab === "strategy" && !viewRunId ? "active" : ""} onClick={() => navigate("strategy")}>编辑策略</button>
        <button disabled={!lastRunId} className={viewRunId ? "active" : ""} onClick={() => lastRunId && openReport(lastRunId)}><BarChartOutlined /> 回测详情</button>
        <button className={tab === "runs" ? "active" : ""} onClick={() => navigate("runs")}><HistoryOutlined /> 回测列表</button>
      </nav> : <span className="version-note">{health?.environment?.quantradar_commit?.slice(0, 8)}</span>}
    </div>
    <main>
      {loading ? <div className="loading-pane"><Spin tip="连接后端中…" /></div> : <>
        {!health && <div className="connection-error">后端连接失败，请检查本地服务。<Button size="small" onClick={() => location.reload()}>重新连接</Button></div>}
        <div style={{ display: tab === "strategy" && !viewRunId ? "block" : "none" }}>
          <StrategyWorkbench onOpenReport={openReport} restoreRun={restoreRun} onNameChange={setName} onRunChange={setLastRunId} />
        </div>
        {viewRunId ? <ReportPage key={viewRunId} runId={viewRunId} onBack={() => navigate("strategy")} onEdit={editRun} /> : <div className={tab === "strategy" ? "" : "page-content"}>
          {tab === "data" && <DataStatus />}
          {tab === "research" && <ResearchMVP />}
          {tab === "runs" && <RunExplorer onOpenReport={openReport} onEdit={editRun} />}
          {tab === "experiments" && <ExperimentCompare />}
        </div>}
      </>}
    </main>
  </div>;
}
