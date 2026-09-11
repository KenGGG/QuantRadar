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
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [releaseError, setReleaseError] = useState<string | null>(null);
  const [actionResult, setActionResult] = useState<unknown>(null);
  const refreshJob = () => getDataHubJob().then((value) => { setJob(value); setJobError(null); }).catch((e) => setJobError(String(e)));
  const refreshRelease = () => getDataHubStatus().then((value) => { setDataHub(value); setReleaseError(null); }).catch((e) => setReleaseError(String(e)));
  const jobAction = (action: "start" | "pause" | "resume" | "stop" | "audit" | "gaps" | "repair" | "publish") => {
    setJobBusy(true);
    setActionError(null);
    setActionMessage(null);
    dataHubJobAction(action).then((result) => { setActionResult(result); setActionMessage((result as { message?: string }).message ?? "操作已完成"); return refreshJob(); })
      .catch((e) => setActionError(String(e))).finally(() => setJobBusy(false));
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
      <div><Typography.Title level={4} style={{ margin: 0 }}>数据状态</Typography.Title><Text type="secondary">已发布覆盖与下载进度</Text></div>
      {jobError && <Alert type="error" showIcon message="任务状态获取失败，以下进度可能已过期" description={jobError} />}
      <Card title="数据覆盖" extra={<Button onClick={refreshRelease}>刷新</Button>}>
        <Table pagination={false} size="middle" rowKey="name" scroll={{ x: 720 }} dataSource={[
          { name: "行情", stocks: undefined, first: undefined, latest: undefined, state: "已接入", note: "覆盖统计待接入" },
          ...[["valuation_daily", "估值"], ["sw_industry_history", "行业"], ["security_lifecycle", "股票基础信息"]].map(([key, name]) => {
            const d = dataHub?.datasets.find(row => row.name === key);
            return { name, stocks: d?.stocks, first: d?.first_date, latest: d?.latest_date, state: d ? "已发布 · 有限制" : "未发布", note: key === "security_lifecycle" ? "日期为上市日期范围" : "" };
          }),
        ]} columns={[
          { title: "数据", dataIndex: "name" },
          { title: "覆盖股票", dataIndex: "stocks", render: v => v == null ? "未统计" : `${Number(v).toLocaleString()} 只` },
          { title: "起始日期", dataIndex: "first", render: v => v ?? "未统计" },
          { title: "最新日期", dataIndex: "latest", render: v => v ?? "未统计" },
          { title: "状态", dataIndex: "state" },
          { title: "备注", dataIndex: "note" },
        ]} />
      </Card>
      <Card title={<Space>采集任务 <Tag color={job?.status === "COOLDOWN" ? "orange" : job?.status === "RUNNING" ? "blue" : "default"}>{job?.status ?? "加载中"}</Tag></Space>} extra={<Button onClick={refreshJob}>刷新</Button>}>
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <Space wrap><Text strong>估值下载</Text></Space>
          <Space wrap>
            <Button type="primary" loading={jobBusy} disabled={busy || running || !job?.counts.failed} onClick={() => jobAction("repair")}>重试失败项（{job?.counts.failed ?? 0}）</Button>
            <Button disabled={busy || running} onClick={() => jobAction("start")}>开始回填</Button>
            <Button disabled={busy || !["RUNNING", "COOLDOWN"].includes(job?.status ?? "")} onClick={() => jobAction("pause")}>暂停</Button>
            <Button disabled={busy || !["PAUSED", "COOLDOWN"].includes(job?.status ?? "")} onClick={() => jobAction("resume")}>继续</Button>
            <Button danger disabled={busy || !["RUNNING", "COOLDOWN"].includes(job?.status ?? "")} onClick={() => jobAction("stop")}>停止</Button>
          </Space>
          {actionError && <Alert type="error" showIcon message="操作失败" description={actionError} />}
          {actionMessage && <Alert type="info" showIcon message={actionMessage} />}
          {job?.status === "COOLDOWN" && <Alert showIcon type="warning" message="来源冷却中" description={`预计恢复时间：${timeLabel(job.governor.cooldown_until as string)}。当前没有发起新请求；以 Governor 的实际恢复结果为准。`} />}
          {job?.status === "PAUSED" && <Alert showIcon type="info" message="任务已暂停，下载结果和待处理进度已保留" />}
          {job?.retry_progress && <Alert showIcon type={job.retry_progress.active ? "info" : job.retry_progress.failed ? "warning" : "success"}
            message={`本轮重试${job.retry_progress.active ? "进行中" : "已结束"}：已尝试 ${job.retry_progress.processed} / ${job.retry_progress.total}，恢复下载 ${job.retry_progress.recovered}，仍失败 ${job.retry_progress.failed}`}
            description={<Progress percent={job.retry_progress.total ? Math.round(job.retry_progress.processed / job.retry_progress.total * 100) : 0} />} />}
          <Progress percent={job?.progress_percentage ?? 0} status={jobError ? "exception" : "normal"} />
          <Row gutter={[16, 16]}>
            <Col xs={12} md={6}><Statistic title="已处理 / 总股票数" value={job?.processed_shards ?? "—"} suffix={`/ ${job?.total_shards ?? "—"}`} /></Col>
            <Col xs={12} md={6}><Statistic title="已下载行数" value={job?.rows_downloaded ?? "—"} /></Col>
            <Col xs={12} md={6}><Statistic title="当前股票" value={job?.current_shard ?? "—"} /></Col>
            <Col xs={12} md={6}><Statistic title="估计剩余时间" value={job?.worker_alive && job?.status === "RUNNING" ? duration(job.estimated_remaining_seconds) : "—"} /></Col>
          </Row>
          <Space wrap>{[["complete", "完成"], ["not_covered", "未覆盖"], ["legal_empty", "合法空值"], ["failed", "失败"], ["pending", "待处理"], ["running", "运行中"]].map(([key, label]) => <Tag key={key} color={key === "failed" && (job?.counts.failed ?? 0) > 0 ? "red" : "default"}>{label} {job ? metric(job.counts[key]) : "—"}</Tag>)}</Space>
          <Text type="secondary">覆盖日期 {job?.coverage.coverage_start ?? "—"} 至 {job?.coverage.coverage_end ?? "—"} · 最近心跳 {timeLabel(job?.last_heartbeat)} · 耗时 {duration(job?.elapsed_seconds)} · 平均速度 {job?.processing_rate ? `${(job.processing_rate * 60).toFixed(1)} 只/分钟` : "—"}</Text>
        </Space>
      </Card>
      <Collapse items={[{ key: "source", label: "技术详情：来源请求与错误", children: <Card size="small" title="来源请求状态">
        <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 3 }}>
          <Descriptions.Item label="来源">{metric(job?.governor.upstream)}</Descriptions.Item>
          <Descriptions.Item label="Circuit">{job ? (job.governor.circuit_open ? "OPEN / COOLDOWN" : "CLOSED") : "—"}</Descriptions.Item>
          <Descriptions.Item label="冷却至">{timeLabel(job?.governor.cooldown_until as string)}</Descriptions.Item>
          <Descriptions.Item label="累计逻辑请求">{metric(job?.governor.logical_requests)}</Descriptions.Item>
          <Descriptions.Item label="SDK 调用次数（HTTP 不透明）">{metric(job?.governor.sdk_attempts_opaque)}</Descriptions.Item>
          <Descriptions.Item label="可观察 HTTP attempts">{metric(job?.governor.observed_http_attempts)}</Descriptions.Item>
          <Descriptions.Item label="observed 403 / 429">{metric(job?.governor.observed_403)} / {metric(job?.governor.observed_429)}</Descriptions.Item>
          <Descriptions.Item label="observed RemoteDisconnected">{metric(job?.governor.observed_remote_disconnected)}</Descriptions.Item>
          <Descriptions.Item label="observed timeout">{metric(job?.governor.observed_timeout)}</Descriptions.Item>
          <Descriptions.Item label="连续受影响股票">{Array.isArray(job?.governor.consecutive_affected_symbols) ? job?.governor.consecutive_affected_symbols.length : "—"}</Descriptions.Item>
          <Descriptions.Item label="最近错误" span={3}><Text type="secondary">{(() => { const last = job?.governor.last_error as Record<string, unknown> | undefined; return last ? `${metric(last.symbol)} · ${metric(last.category)} · ${metric(last.message)}` : "—"; })()}</Text></Descriptions.Item>
        </Descriptions>
      </Card> }]} />
      <Card title="检查与发布" extra={<Button onClick={refreshRelease}>刷新版本</Button>}>
        <Alert showIcon type={job?.counts.failed ? "warning" : "info"} message={job?.counts.failed ? `暂不能发布：还有 ${job.counts.failed} 项采集失败` : "下载结束不代表检查通过，发布时仍须执行数据检查"}
          style={{ marginBottom: 16 }} />
        <Space wrap style={{ marginBottom: 16 }}>
          <Button disabled={busy || job?.status !== "COMPLETED"} onClick={() => jobAction("audit")}>审计</Button>
          <Button disabled={busy || running} onClick={() => jobAction("gaps")}>查看缺口</Button>
          <Button disabled={busy || running || job?.status !== "COMPLETED" || !!dataHub?.audit_error || !!job?.counts.failed || !!job?.counts.pending} onClick={() => jobAction("publish")}>检查并发布</Button>
        </Space>
        {releaseError && <Alert type="error" message="正式版本状态读取失败" description={releaseError} />}
        {dataHub?.audit_error && <Alert type="warning" showIcon message="正式版本审计存在异常" description={dataHub.audit_error} style={{ marginBottom: 16 }} />}
        <Descriptions size="small" column={{ xs: 1, md: 2 }} style={{ marginBottom: 16 }}>
          <Descriptions.Item label="当前 release">{dataHub?.current_release?.release_id ?? "—"}</Descriptions.Item>
          <Descriptions.Item label="上次成功更新">{timeLabel(dataHub?.last_success)}</Descriptions.Item>
        </Descriptions>
        <Collapse items={[{ key: "audit", label: "技术详情：正式版本覆盖与审计", children: <Table size="small" pagination={false} scroll={{ x: 1750 }} locale={{ emptyText: "暂无可展示的正式数据集审计；请查看上方状态" }} rowKey="name" dataSource={dataHub?.datasets ?? []} columns={[
          { title: "数据集", dataIndex: "name" }, { title: "历史时点可靠性（PIT）", render: (_v, row) => <Space direction="vertical" size={0}><Tag color={row.pit_status === "PASS" ? "green" : "orange"}>{row.pit_status ?? "未审计"}</Tag><Text type="secondary">未通过严格 PIT：{row.partial_rows == null ? "未统计" : `${row.partial_rows.toLocaleString()} 行`}</Text></Space> },
          { title: "来源", dataIndex: "source", render: (v) => Array.isArray(v) ? v.join(", ") : "-" },
          { title: "历史起点", dataIndex: "first_date" }, { title: "最新日期", dataIndex: "latest_date" },
          { title: "股票覆盖", dataIndex: "stocks" }, { title: "行数", render: (_v, row) => row.row_count ?? row.rows ?? "未统计" },
          { title: "已入库字段空值", render: (_v, row) => row.source_nulls ? <Space direction="vertical" size={0}>{Object.entries(row.source_nulls).map(([field, count]) => <Text key={field}>{field}：{count == null ? "当前版本未提供" : `${count.toLocaleString()} 个空值`}</Text>)}</Space> : "未统计（不代表无缺失）" },
          { title: "股票 / 日期覆盖缺口", render: (_v, row) => typeof row.coverage?.source_not_covered_stock_days === "number" ? `${row.coverage.source_not_covered_stock_days.toLocaleString()} 个股票交易日未覆盖` : "未统计（不代表完整覆盖）" },
          { title: "冲突 / 修订", render: (_v, row) => row.name === "security_lifecycle" ? `退市股票: ${row.delisted_stocks ?? "—"}` : `冲突: ${row.conflicts ?? "未统计"}；修订: ${row.history_revision_count ?? "未统计"}` },
        ]} /> }]} />
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
