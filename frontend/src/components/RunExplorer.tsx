import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Col, Descriptions, Empty, Input, Row, Space, Table, Tag, Typography } from "antd";
import { listRuns, submitAsync, getRun, type RunRecord } from "../api";

const { Text } = Typography;

const statusColor: Record<string, string> = {
  PENDING: "default",
  RUNNING: "processing",
  SUCCESS: "success",
  FAILED: "error",
};

export function RunExplorer({
  onOpenReport,
}: {
  onOpenReport: (runId: string) => void;
}) {
  const [security, setSecurity] = useState("600519.XSHG");
  const [start, setStart] = useState("2023-01-03");
  const [end, setEnd] = useState("2023-03-31");
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [selected, setSelected] = useState<RunRecord | null>(null);
  const [pollId, setPollId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [loadingList, setLoadingList] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(() => {
    setLoadingList(true);
    listRuns(50)
      .then((r) => setRuns(r.runs))
      .catch((e) => setError(String(e)))
      .finally(() => setLoadingList(false));
  }, []);

  useEffect(() => {
    refresh();
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [refresh]);

  const onPoll = useCallback((runId: string) => {
    setPollId(runId);
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const rec = await getRun(runId);
        setSelected(rec);
        if (rec.status === "SUCCESS" || rec.status === "FAILED") {
          if (timer.current) clearInterval(timer.current);
          setPollId(null);
          refresh();
        }
      } catch {
        /* ignore transient */
      }
    }, 1500);
  }, [refresh]);

  const onSubmit = () => {
    setSubmitting(true);
    setError(null);
    submitAsync({ security, start_date: start, end_date: end, initial_cash: 500000, frequency: "day" })
      .then((r) => {
        refresh();
        onPoll(r.run_id);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setSubmitting(false));
  };

  const viewRun = (rec: RunRecord) => {
    setSelected(rec);
    if (rec.status === "RUNNING" || rec.status === "PENDING") onPoll(rec.run_id);
  };

  return (
    <Row gutter={12}>
      <Col xs={24} lg={9}>
        <Card size="small" title="异步提交回测（Worker 执行，结果落 PostgreSQL）" style={{ marginBottom: 12 }}>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Input addonBefore="标的" value={security} onChange={(e) => setSecurity(e.target.value)} />
            <Input addonBefore="起始" value={start} onChange={(e) => setStart(e.target.value)} />
            <Input addonBefore="结束" value={end} onChange={(e) => setEnd(e.target.value)} />
            <Button type="primary" loading={submitting} onClick={onSubmit}>提交异步回测</Button>
            {error && <Alert type="error" showIcon message={error} />}
          </Space>
        </Card>
        <Card size="small" title="运行记录" loading={loadingList}>
          <Table<RunRecord>
            size="small"
            rowKey="run_id"
            pagination={{ pageSize: 10 }}
            dataSource={runs}
            onRow={(rec) => ({ onClick: () => viewRun(rec), style: { cursor: "pointer" } })}
            columns={[
              { title: "run_id", dataIndex: "run_id", render: (v) => <Text ellipsis style={{ maxWidth: 120, display: "inline-block" }}>{v}</Text> },
              {
                title: "状态",
                dataIndex: "status",
                render: (s: string) => <Tag color={statusColor[s] ?? "default"}>{s}</Tag>,
              },
              {
                title: "结果哈希",
                dataIndex: "result_hash",
                render: (v) => (v ? <Text ellipsis style={{ maxWidth: 90, display: "inline-block" }}>{v.slice(0, 12)}</Text> : "-"),
              },
            ]}
          />
        </Card>
      </Col>
      <Col xs={24} lg={15}>
        <Card size="small" title={selected ? `运行详情 ${selected.run_id}` : "运行详情"}>
          {pollId && <Alert type="info" showIcon message="后台执行中，每 1.5s 自动刷新状态…" style={{ marginBottom: 12 }} />}
          {!selected && <Empty description="从左侧选择一条运行记录查看详情" />}
          {selected && (
            <>
              <Space style={{ marginBottom: 8 }}>
                <Tag color={statusColor[selected.status] ?? "default"}>{selected.status}</Tag>
                {selected.status === "SUCCESS" && (
                  <Button type="link" size="small" onClick={() => onOpenReport(selected.run_id)}>
                    打开完整报告 →
                  </Button>
                )}
                {selected.error && <Text type="danger">{selected.error}</Text>}
              </Space>
              <RunSummary run={selected} onOpenReport={onOpenReport} />
            </>
          )}
        </Card>
      </Col>
    </Row>
  );
}

/** 运行记录详情摘要：仅展示配置/结果哈希与少数 BulletTrade 原生指标，完整图表见「打开完整报告」。 */
function RunSummary({
  run,
  onOpenReport,
}: {
  run: RunRecord;
  onOpenReport: (runId: string) => void;
}) {
  const cfg = (run.config || {}) as Record<string, unknown>;
  const m = (run.metrics || {}) as Record<string, unknown>;
  return (
    <Card size="small" title={`运行详情 ${run.run_id}`}>
      <Descriptions size="small" column={2} bordered>
        <Descriptions.Item label="区间">
          {String(cfg.start_date ?? "-")} → {String(cfg.end_date ?? "-")}
        </Descriptions.Item>
        <Descriptions.Item label="初始资金">{fmtNum(Number(cfg.initial_cash ?? 0), 0)}</Descriptions.Item>
        <Descriptions.Item label="Benchmark">{String(cfg.benchmark ?? "-")}</Descriptions.Item>
        <Descriptions.Item label="复权">{String(cfg.fq ?? "-")}</Descriptions.Item>
        <Descriptions.Item label="策略收益">{fmtMetric(m["策略收益"])}</Descriptions.Item>
        <Descriptions.Item label="最大回撤">{fmtMetric(m["最大回撤"])}</Descriptions.Item>
        <Descriptions.Item label="夏普比率">{fmtMetric(m["夏普比率"])}</Descriptions.Item>
        <Descriptions.Item label="结果哈希"><Text copyable>{run.result_hash ?? "-"}</Text></Descriptions.Item>
      </Descriptions>
      <Button type="primary" style={{ marginTop: 8 }} onClick={() => onOpenReport(run.run_id)}>
        打开完整回测报告（BulletTrade 原生）
      </Button>
    </Card>
  );
}

function fmtNum(v: number, digits = 2): string {
  if (!v && v !== 0) return "-";
  return v.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

function fmtMetric(v: unknown): string {
  if (v == null || v === "") return "-";
  if (typeof v === "number") return v.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  return String(v);
}
