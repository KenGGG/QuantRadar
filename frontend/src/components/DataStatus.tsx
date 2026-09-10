import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Input,
  InputNumber,
  Row,
  Spin,
  Collapse,
  Progress,
  Space,
  Statistic,
  Tag,
  Table,
  Typography,
} from "antd";
import ReactECharts from "echarts-for-react";
import {
  getHealth,
  getDataHubStatus,
  getDataHubJob,
  dataHubJobAction,
  getPrice,
  type Environment,
  type DataHubStatus,
  type DataHubJob,
  type HealthResp,
  type PriceRow,
} from "../api";

const { Text } = Typography;

export function DataStatus() {
  const [health, setHealth] = useState<HealthResp | null>(null);
  const [security, setSecurity] = useState("600519.XSHG");
  const [lookback, setLookback] = useState(120);
  const [rows, setRows] = useState<PriceRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [dataHub, setDataHub] = useState<DataHubStatus | null>(null);
  const [job, setJob] = useState<DataHubJob | null>(null);
  const [jobBusy, setJobBusy] = useState(false);
  const [jobError, setJobError] = useState<string | null>(null);
  const [releaseError, setReleaseError] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<unknown>(null);
  const refreshJob = () => getDataHubJob().then((value) => { setJob(value); setJobError(null); }).catch((e) => setJobError(String(e)));
  const refreshRelease = () => getDataHubStatus().then((value) => { setDataHub(value); setReleaseError(null); }).catch((e) => setReleaseError(String(e)));
  const jobAction = (action: "start" | "pause" | "resume" | "stop" | "audit" | "gaps" | "repair" | "publish") => {
    setJobBusy(true);
    dataHubJobAction(action).then((result) => { setActionResult(result); return refreshJob(); })
      .catch((e) => setJobError(String(e))).finally(() => setJobBusy(false));
  };
  const onHealth = () => {
    setError(null);
    getHealth()
      .then(setHealth)
      .catch((e) => setError(String(e)));
  };

  const onQuery = () => {
    setLoading(true);
    setError(null);
    // 取最新窗口：仅传 count，后端返回表尾最近 N 个交易日（反映 investment_data 当前能展示的数据）
    getPrice({
      security,
      count: lookback,
      fields: "open,high,low,close,volume",
      fq: "none",
    })
      .then((r) => setRows(r.rows))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refreshRelease();
    refreshJob();
    const timer = window.setInterval(refreshJob, 4000);
    return () => window.clearInterval(timer);
  }, []);
  const busy = jobBusy || !job || !!jobError;
  const running = ["RUNNING", "COOLDOWN", "PAUSING", "AUDITING", "PUBLISHING"].includes(job?.status ?? "");
  const metric = (value: unknown) => value == null ? "—" : String(value);
  const timeLabel = (value?: string | null) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
  const duration = (value?: number | null) => value && value > 0 ? `${Math.ceil(value / 60).toLocaleString()} 分钟` : "—";
  const env = (health?.environment ?? {}) as Environment;

  const dates = rows.map((r) => r.date);
  const kline = rows.map((r) => [
    Number(r.open),
    Number(r.close),
    Number(r.low),
    Number(r.high),
  ]);
  const volumes = rows.map((r) => Number(r.volume));
  const chartOption = {
    animation: false,
    tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    grid: [
      { left: 56, right: 16, top: 16, height: "58%" },
      { left: 56, right: 16, top: "76%", height: "16%" },
    ],
    xAxis: [
      { type: "category", data: dates, gridIndex: 0, axisLabel: { show: false }, boundaryGap: true },
      { type: "category", data: dates, gridIndex: 1, axisLabel: { show: false }, boundaryGap: true },
    ],
    yAxis: [
      { scale: true, gridIndex: 0, splitArea: { show: true } },
      { scale: true, gridIndex: 1, splitNumber: 2 },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 0, end: 100 },
    ],
    series: [
      {
        type: "candlestick",
        data: kline,
        gridIndex: 0,
        itemStyle: {
          color: "#ef232a",
          color0: "#14b143",
          borderColor: "#ef232a",
          borderColor0: "#14b143",
        },
      },
      {
        type: "bar",
        data: volumes,
        gridIndex: 1,
        itemStyle: { color: "#5470c6" },
      },
    ],
  };

  return (
    <div style={{ display: "grid", gap: 16, minWidth: 0 }}>
      <div><Typography.Title level={4} style={{ margin: 0 }}>数据状态</Typography.Title><Text type="secondary">采集进度每 4 秒刷新 · 下载结果经审计和发布后才用于研究</Text></div>
      {jobError && <Alert type="error" showIcon message="任务状态获取失败，以下进度可能已过期" description={jobError} />}
      <Card title={<Space>采集任务 <Tag color={job?.status === "COOLDOWN" ? "orange" : job?.status === "RUNNING" ? "blue" : "default"}>{job?.status ?? "加载中"}</Tag></Space>} extra={<Button onClick={refreshJob}>刷新</Button>}>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Space wrap><Text strong>{job?.dataset ?? "valuation_daily"}</Text><Text type="secondary">Job: {job?.job_id ?? "—"} · 默认续传，保留已完成结果</Text></Space>
          <Space wrap>
            <Button type="primary" disabled={busy || running} onClick={() => jobAction("start")}>开始回填</Button>
            <Button disabled={busy || !["RUNNING", "COOLDOWN"].includes(job?.status ?? "")} onClick={() => jobAction("pause")}>暂停</Button>
            <Button disabled={busy || !["PAUSED", "COOLDOWN"].includes(job?.status ?? "")} onClick={() => jobAction("resume")}>继续</Button>
            <Button danger disabled={busy || !["RUNNING", "COOLDOWN"].includes(job?.status ?? "")} onClick={() => jobAction("stop")}>停止</Button>
          </Space>
          {job?.status === "COOLDOWN" && <Alert showIcon type="warning" message="来源冷却中" description={`预计恢复时间：${timeLabel(job.governor.cooldown_until as string)}。当前没有发起新请求；以 Governor 的实际恢复结果为准。`} />}
          {job?.status === "PAUSED" && <Alert showIcon type="info" message="任务已暂停，下载结果和待处理进度已保留" />}
          {job?.worker_alive === false && <Alert showIcon type="warning" message="采集进程当前未运行，页面展示已保存的进度" description="Governor 冷却状态不代表后台仍在运行。已完成数据保留；任务恢复控制仍需完成验收。" />}
          <Progress percent={job?.progress_percentage ?? 0} status={jobError ? "exception" : "normal"} />
          <Row gutter={[16, 16]}>
            <Col xs={12} md={6}><Statistic title="已处理 / 总股票数" value={job?.processed_shards ?? "—"} suffix={`/ ${job?.total_shards ?? "—"}`} /></Col>
            <Col xs={12} md={6}><Statistic title="已下载行数" value={job?.rows_downloaded ?? "—"} /></Col>
            <Col xs={12} md={6}><Statistic title="当前股票" value={job?.current_shard ?? "—"} /></Col>
            <Col xs={12} md={6}><Statistic title="估计剩余时间" value={job?.worker_alive && job?.status === "RUNNING" ? duration(job.estimated_remaining_seconds) : "—"} /></Col>
          </Row>
          <Space wrap>{[["complete", "完成"], ["not_covered", "未覆盖"], ["legal_empty", "合法空值"], ["failed", "失败"], ["pending", "待处理"]].map(([key, label]) => <Tag key={key} color={key === "failed" && (job?.counts.failed ?? 0) > 0 ? "red" : "default"}>{label} {job ? metric(job.counts[key]) : "—"}</Tag>)}</Space>
          <Text type="secondary">覆盖日期 {job?.coverage.coverage_start ?? "—"} 至 {job?.coverage.coverage_end ?? "—"} · 最近心跳 {timeLabel(job?.last_heartbeat)} · 耗时 {duration(job?.elapsed_seconds)} · 平均速度 {job?.processing_rate ? `${(job.processing_rate * 60).toFixed(1)} 只/分钟` : "—"}</Text>
        </Space>
      </Card>
      <Card size="small" title="来源请求状态 · Request Governor">
        <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
          <Descriptions.Item label="来源">{metric(job?.governor.upstream)}</Descriptions.Item>
          <Descriptions.Item label="Circuit">{job ? (job.governor.circuit_open ? "OPEN / COOLDOWN" : "CLOSED") : "—"}</Descriptions.Item>
          <Descriptions.Item label="冷却至">{timeLabel(job?.governor.cooldown_until as string)}</Descriptions.Item>
          <Descriptions.Item label="累计逻辑请求">{metric(job?.governor.logical_requests)}</Descriptions.Item>
          <Descriptions.Item label="HTTP attempts（可观察）">{metric(job?.governor.actual_http_attempts)}</Descriptions.Item>
          <Descriptions.Item label="403 / 429">{metric(job?.governor["403"])} / {metric(job?.governor["429"])}</Descriptions.Item>
          <Descriptions.Item label="RemoteDisconnected">{metric(job?.governor.RemoteDisconnected)}</Descriptions.Item>
          <Descriptions.Item label="Timeout">{metric(job?.governor.timeout)}</Descriptions.Item>
          <Descriptions.Item label="连续受影响股票">{Array.isArray(job?.governor.consecutive_affected_symbols) ? job?.governor.consecutive_affected_symbols.length : "—"}</Descriptions.Item>
          <Descriptions.Item label="最近错误" span={3}><Text type="secondary">{(() => { const last = job?.governor.last_error as Record<string, unknown> | undefined; return last ? `${metric(last.symbol)} · ${metric(last.category)} · ${metric(last.message)}` : "—"; })()}</Text></Descriptions.Item>
        </Descriptions>
      </Card>
      <Card title="正式研究数据与覆盖" extra={<Button onClick={refreshRelease}>刷新版本</Button>}>
        <Space wrap style={{ marginBottom: 16 }}>
          <Button disabled={busy || job?.status !== "COMPLETED"} onClick={() => jobAction("audit")}>审计</Button>
          <Button disabled={busy || running} onClick={() => jobAction("gaps")}>查看缺口</Button>
          <Button disabled={busy || running || !(job?.counts.failed)} onClick={() => jobAction("repair")}>修复失败</Button>
          <Button disabled={busy || running || job?.status !== "COMPLETED" || !!dataHub?.audit_error} onClick={() => jobAction("publish")}>发布</Button>
        </Space>
        <Alert type="info" showIcon message="采集进度不等于正式覆盖；研究使用下方 release 锁定的数据。PIT / 质量限制以各数据集实测审计为准。" style={{ marginBottom: 16 }} />
        {releaseError && <Alert type="error" message="正式版本状态读取失败" description={releaseError} />}
        {dataHub?.audit_error && <Alert type="warning" showIcon message="正式版本审计存在异常" description={dataHub.audit_error} style={{ marginBottom: 16 }} />}
        <Descriptions size="small" column={{ xs: 1, md: 2 }} style={{ marginBottom: 16 }}>
          <Descriptions.Item label="当前 release">{dataHub?.current_release?.release_id ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="上次成功更新">{timeLabel(dataHub?.last_success)}</Descriptions.Item>
        </Descriptions>
        <Table size="small" pagination={false} scroll={{ x: 1150 }} locale={{ emptyText: "暂无可展示的正式数据集审计；请查看上方状态" }} rowKey="name" dataSource={dataHub?.datasets ?? []} columns={[
          { title: "数据集", dataIndex: "name" }, { title: "PIT", dataIndex: "pit_status" },
          { title: "来源", dataIndex: "source", render: (v) => Array.isArray(v) ? v.join(", ") : "-" },
          { title: "历史起点", dataIndex: "first_date" }, { title: "最新日期", dataIndex: "latest_date" },
          { title: "股票覆盖", dataIndex: "stocks" }, { title: "行数", dataIndex: "rows", render: (v, row) => v ?? row.row_count ?? "-" },
          { title: "缺失 / PARTIAL", render: (_v, row) => row.source_nulls ? JSON.stringify({ ...row.source_nulls, source_not_covered: row.coverage?.source_not_covered_stock_days }) : (row.partial_rows ?? "-") },
          { title: "冲突 / 修订", render: (_v, row) => row.name === "security_lifecycle" ? `退市股票: ${row.delisted_stocks ?? "—"}` : `冲突: ${row.conflicts ?? "—"}；修订: ${row.history_revision_count ?? "—"}` },
        ]} />
      </Card>

      {actionResult != null && <Collapse items={[{ key: "result", label: "最近操作结果", children: <pre style={{ maxHeight: 350, overflow: "auto", whiteSpace: "pre-wrap" }}>{JSON.stringify(actionResult, null, 2)}</pre> }]} />}
      <Collapse items={[{ key: "diagnostics", label: "版本与连接诊断", children: <Space direction="vertical" style={{ width: "100%" }}>
        <Button onClick={onHealth}>检查基础数据连接</Button>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="连接">{health ? "已连接" : "尚未检查"}</Descriptions.Item>
          <Descriptions.Item label="基础 Dolt commit"><Text copyable>{dataHub?.current_release?.base_commit ?? "—"}</Text></Descriptions.Item>
          <Descriptions.Item label="补充 Dolt commit"><Text copyable>{dataHub?.current_release?.supplemental_commit ?? "—"}</Text></Descriptions.Item>
          <Descriptions.Item label="Schema hash">{env.schema_hash ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="上次发布失败">{dataHub?.last_failure ? JSON.stringify(dataHub.last_failure.failures) : "—"}</Descriptions.Item>
        </Descriptions>
      </Space> }, { key: "quotes", label: "行情查询（按需加载）", children: (
      <Card size="small" title="行情查询（真实数据，经 InvestmentDataProvider）">
        <Row gutter={8} align="middle" style={{ marginBottom: 12 }}>
          <Col>
            <Input
              addonBefore="标的"
              value={security}
              onChange={(e) => setSecurity(e.target.value)}
              style={{ width: 220 }}
              placeholder="如 600519.XSHG"
            />
          </Col>
          <Col>
            <InputNumber
              addonBefore="交易日数"
              min={20}
              max={500}
              step={10}
              value={lookback}
              onChange={(v) => setLookback(typeof v === "number" ? v : 120)}
              style={{ width: 140 }}
            />
          </Col>
          <Col>
            <Button type="primary" loading={loading} onClick={onQuery}>
              查询最新行情
            </Button>
          </Col>
        </Row>
        {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
        {loading && <Spin />}
        {rows.length > 0 && (
          <>
            <ReactECharts option={chartOption} style={{ height: 420, width: "100%" }} notMerge />
            <Table<PriceRow>
              size="small"
              rowKey="date"
              pagination={false}
              dataSource={rows.slice(-20)}
              scroll={{ x: "max-content" }}
              style={{ marginTop: 12 }}
              columns={[
                { title: "日期", dataIndex: "date" },
                { title: "开盘", dataIndex: "open", render: (v) => (v == null ? "-" : Number(v).toFixed(2)) },
                { title: "最高", dataIndex: "high", render: (v) => (v == null ? "-" : Number(v).toFixed(2)) },
                { title: "最低", dataIndex: "low", render: (v) => (v == null ? "-" : Number(v).toFixed(2)) },
                { title: "收盘", dataIndex: "close", render: (v) => (v == null ? "-" : Number(v).toFixed(2)) },
                {
                  title: "成交量",
                  dataIndex: "volume",
                  render: (v) => (v == null ? "-" : Number(v).toLocaleString("zh-CN")),
                },
              ]}
            />
          </>
        )}
      </Card>
      ) }]} />
    </div>
  );
}
