import { useEffect, useState } from "react";
import { Layout, Menu, Spin, Typography } from "antd";
import {
  ApiOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  CodeOutlined,
} from "@ant-design/icons";
import { getHealth, type HealthResp } from "./api";
import { DataStatus } from "./components/DataStatus";
import { StrategyWorkbench } from "./components/StrategyWorkbench";
import { RunExplorer } from "./components/RunExplorer";
import { ExperimentCompare } from "./components/ExperimentCompare";
import { ReportPage } from "./components/ReportPage";

const { Sider, Content, Header } = Layout;
const { Title, Text } = Typography;

type TabKey = "data" | "strategy" | "runs" | "experiments";

export function App() {
  const [health, setHealth] = useState<HealthResp | null>(null);
  const [tab, setTab] = useState<TabKey>("data");
  const [loading, setLoading] = useState(true);
  const [viewRunId, setViewRunId] = useState<string | null>(null);

  const openReport = (runId: string) => {
    setViewRunId(runId);
    setTab("strategy");
  };

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth(null))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="dark" width={220} breakpoint="lg" collapsedWidth={0}>
        <div className="app-logo">量子雷达 · QuantRadar</div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[tab]}
          onClick={(e) => setTab(e.key as TabKey)}
          items={[
            { key: "data", icon: <ApiOutlined />, label: "数据状态" },
            { key: "strategy", icon: <CodeOutlined />, label: "策略回测" },
            { key: "runs", icon: <FileSearchOutlined />, label: "运行记录" },
            { key: "experiments", icon: <ExperimentOutlined />, label: "实验对比" },
          ]}
        />
      </Sider>
      <Layout>
        <Header style={{ background: "#fff", paddingInline: 24, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Title level={4} style={{ margin: 0 }}>
            本地真实数据 · 可审计 · 可复现 的 A 股量化研究平台
          </Title>
          <Text type="secondary">
            数据源：{health ? health.provider : "未连接"}
            {health?.environment?.quantradar_commit ? ` · commit ${health.environment.quantradar_commit.slice(0, 8)}` : ""}
          </Text>
        </Header>
        <Content className="content-pad">
          {loading ? (
            <div style={{ textAlign: "center", marginTop: 80 }}>
              <Spin tip="连接后端中..." />
            </div>
          ) : viewRunId ? (
            <ReportPage runId={viewRunId} onBack={() => setViewRunId(null)} />
          ) : (
            <>
              {tab === "data" && <DataStatus />}
              {tab === "strategy" && <StrategyWorkbench onOpenReport={openReport} />}
              {tab === "runs" && <RunExplorer onOpenReport={openReport} />}
              {tab === "experiments" && <ExperimentCompare />}
            </>
          )}
        </Content>
      </Layout>
    </Layout>
  );
}
