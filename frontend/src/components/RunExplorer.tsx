import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Col, Empty, Input, Row, Space, Table, Tag, Typography } from "antd";
import { listRuns, submitAsync, getRun, type RunRecord, type Snapshot } from "../api";
import { ResultsView } from "./ResultsView";

const { Text } = Typography;

const statusColor: Record<string, string> = {
  PENDING: "default",
  RUNNING: "processing",
  SUCCESS: "success",
  FAILED: "error",
};

export function RunExplorer() {
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

  const snapshot: Snapshot | null | undefined = selected?.snapshot;

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
                {selected.error && <Text type="danger">{selected.error}</Text>}
              </Space>
              <ResultsView snapshot={snapshot} />
            </>
          )}
        </Card>
      </Col>
    </Row>
  );
}
