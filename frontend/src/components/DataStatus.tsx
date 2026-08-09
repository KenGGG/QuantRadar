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
  Table,
  Typography,
} from "antd";
import ReactECharts from "echarts-for-react";
import {
  getHealth,
  getPrice,
  pullData,
  type Environment,
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

  const [pulling, setPulling] = useState(false);
  const [pullResult, setPullResult] = useState<{ ok: boolean; message: string } | null>(null);

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

  const onPull = () => {
    setPulling(true);
    setPullResult(null);
    setError(null);
    pullData()
      .then((r) => {
        setPullResult({ ok: r.ok, message: r.message });
        if (r.ok) onHealth(); // 拉取成功后刷新，使「最新数据日期」同步
      })
      .catch((e) => setPullResult({ ok: false, message: String(e) }))
      .finally(() => setPulling(false));
  };

  // 打开即自动加载默认标的的最新 K 线
  useEffect(() => {
    onQuery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    <div>
      <Card size="small" title="数据源状态 / 审计环境" style={{ marginBottom: 12 }}>
        <Row gutter={12} align="middle">
          <Col flex="auto">
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="连接状态">
                {health ? <Text type="success">已连接</Text> : <Text type="warning">未连接</Text>}
              </Descriptions.Item>
              <Descriptions.Item label="Provider">{health?.provider ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="Dolt commit">
                <Text copyable>{env.dolt_commit ?? "-"}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="Schema 哈希">
                <Text copyable>{env.schema_hash ?? "-"}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="最新数据日期">
                <Text strong>{env.latest_data_date ?? "-"}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="Provider 版本">{env.provider_version ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="BulletTrade">{env.bullettrade_commit ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="QuantRadar commit">
                <Text copyable>{env.quantradar_commit ?? "-"}</Text>
              </Descriptions.Item>
            </Descriptions>
          </Col>
          <Col>
            <Button type="primary" onClick={onHealth}>
              刷新状态
            </Button>
            <Button style={{ marginTop: 8 }} loading={pulling} onClick={onPull}>
              更新数据
            </Button>
          </Col>
        </Row>
        {pullResult && (
          <Alert
            style={{ marginTop: 12 }}
            type={pullResult.ok ? "success" : "error"}
            showIcon
            message={pullResult.ok ? "更新数据成功（已刷新状态）" : "更新数据失败"}
            description={<span style={{ whiteSpace: "pre-wrap" }}>{pullResult.message}</span>}
          />
        )}
        {!health && !error && (
          <Button style={{ marginTop: 12 }} onClick={onHealth}>
            连接数据源
          </Button>
        )}
      </Card>

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
    </div>
  );
}
