import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Row,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  getRun,
  getRunArtifacts,
  getRunArtifactUrl,
  getRunReportUrl,
  type RunRecord,
  type RunArtifactsResp,
  type Snapshot,
} from "../api";

const { Text, Title } = Typography;

const statusColor: Record<string, string> = {
  PENDING: "default",
  RUNNING: "processing",
  SUCCESS: "success",
  FAILED: "error",
};

/**
 * 完整回测报告页：直接嵌入 BulletTrade 原生 HTML 报告（report.html / standard_report.html），
 * 不在前端重算/重绘任何指标与图表（复用 BulletTrade 原生报告）。下方附 QuantRadar 审计面板与产物清单。
 */
export function ReportPage({
  runId,
  onBack,
}: {
  runId: string;
  onBack: () => void;
}) {
  const [run, setRun] = useState<RunRecord | null>(null);
  const [arts, setArts] = useState<RunArtifactsResp | null>(null);
  const [which, setWhich] = useState<"full" | "standard">("standard");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    getRun(runId)
      .then(setRun)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
    getRunArtifacts(runId)
      .then(setArts)
      .catch(() => setArts(null));
  }, [runId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (loading) {
    return (
      <div style={{ textAlign: "center", marginTop: 80 }}>
        <Spin tip="加载运行结果…" />
      </div>
    );
  }

  if (error) {
    return <Alert type="error" showIcon message={error} />;
  }

  if (!run) {
    return <Empty description="运行记录不存在" />;
  }

  if (run.status !== "SUCCESS") {
    return (
      <Card size="small">
        <Space direction="vertical" style={{ width: "100%" }}>
          <Tag color={statusColor[run.status] ?? "default"}>{run.status}</Tag>
          {run.status === "FAILED" && run.error && (
            <Alert type="error" showIcon message="回测失败" description={<pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{run.error}</pre>} />
          )}
          {run.status !== "FAILED" && <Text type="secondary">后台回测执行中，请稍后刷新或返回重新打开。</Text>}
          <Button onClick={onBack}>← 返回</Button>
        </Space>
      </Card>
    );
  }

  const snapshot: Snapshot | null | undefined = run.snapshot;
  const cfg = (run.config || {}) as Record<string, unknown>;
  const env = (snapshot?.environment || {}) as Record<string, unknown>;
  const reportSrc = getRunReportUrl(runId, which);

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>
          回测报告 · {runId}
        </Title>
        <Space>
          <Button
            type={which === "standard" ? "primary" : "default"}
            onClick={() => setWhich("standard")}
          >
            聚宽风格
          </Button>
          <Button type={which === "full" ? "primary" : "default"} onClick={() => setWhich("full")}>
            详细报告
          </Button>
          <Button onClick={onBack}>← 返回</Button>
        </Space>
      </Row>

      {/* BulletTrade 原生 HTML 报告（直接嵌入，不重算指标） */}
      <Card size="small" style={{ marginBottom: 12 }}>
        <iframe
          title="BulletTrade 回测报告"
          src={reportSrc}
          style={{ width: "100%", height: "900px", border: "1px solid #e8e8e8", borderRadius: 6 }}
        />
      </Card>

      {/* 产物清单 */}
      <Card size="small" title="报告产物 Artifacts（runs 目录）" style={{ marginBottom: 12 }}>
        {arts ? (
          <Table<(typeof arts.artifacts)[number]>
            size="small"
            rowKey="name"
            pagination={false}
            dataSource={arts.artifacts}
            columns={[
              {
                title: "文件",
                dataIndex: "name",
                render: (v: string, r) =>
                  r.is_report ? (
                    <a href={getRunReportUrl(runId, r.name === "standard_report.html" ? "standard" : "full")} target="_blank" rel="noreferrer">
                      {v}
                    </a>
                  ) : (
                    <a
                      href={getRunArtifactUrl(runId, v)}
                      target="_blank"
                      rel="noreferrer"
                      download={v}
                    >
                      {v}
                    </a>
                  ),
              },
              { title: "类型", dataIndex: "ext", width: 80 },
              {
                title: "大小",
                dataIndex: "size",
                width: 110,
                render: (s: number | null) => (s == null ? "-" : `${(s / 1024).toFixed(1)} KB`),
              },
            ]}
          />
        ) : (
          <Text type="secondary">产物清单不可用</Text>
        )}
      </Card>

      {/* QuantRadar 附加审计信息（不替代 BulletTrade 原生 metrics） */}
      <Card size="small" title="QuantRadar 审计 / 可复现（附加信息）" style={{ marginBottom: 12 }}>
        <Descriptions size="small" column={2} bordered>
          <Descriptions.Item label="起始">{String(cfg.start_date ?? "-")}</Descriptions.Item>
          <Descriptions.Item label="结束">{String(cfg.end_date ?? "-")}</Descriptions.Item>
          <Descriptions.Item label="初始资金">{fmtNum(Number(cfg.initial_cash ?? 0), 0)}</Descriptions.Item>
          <Descriptions.Item label="频率">{String(cfg.frequency ?? "-")}</Descriptions.Item>
          <Descriptions.Item label="Benchmark">{String(cfg.benchmark ?? "-")}</Descriptions.Item>
          <Descriptions.Item label="复权">{String(cfg.fq ?? "-")}</Descriptions.Item>
          <Descriptions.Item label="数据 as-of">{snapshot?.data_asof ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="记录数">{snapshot?.records_count ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="数据源">{String(env.provider ?? "-")}</Descriptions.Item>
          <Descriptions.Item label="Provider 版本">{String(env.provider_version ?? "-")}</Descriptions.Item>
          <Descriptions.Item label="Dolt commit"><Text copyable>{String(env.dolt_commit ?? "-")}</Text></Descriptions.Item>
          <Descriptions.Item label="Schema 哈希"><Text copyable>{String(env.schema_hash ?? "-")}</Text></Descriptions.Item>
          <Descriptions.Item label="BulletTrade commit">{String(env.bullettrade_commit ?? "-")}</Descriptions.Item>
          <Descriptions.Item label="QuantRadar commit"><Text copyable>{String(env.quantradar_commit ?? "-")}</Text></Descriptions.Item>
          <Descriptions.Item label="配置哈希"><Text copyable>{snapshot?.config_hash}</Text></Descriptions.Item>
          <Descriptions.Item label="策略哈希"><Text copyable>{snapshot?.strategy_hash}</Text></Descriptions.Item>
          <Descriptions.Item label="结果哈希"><Text copyable>{snapshot?.result_hash}</Text></Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  );
}

function fmtNum(v: number, digits = 2): string {
  if (!v && v !== 0) return "-";
  return v.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}
