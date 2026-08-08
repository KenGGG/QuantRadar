import { useState } from "react";
import { Alert, Button, Card, Col, Descriptions, Input, Row, Spin, Table, Typography } from "antd";
import { getHealth, getPrice, type HealthResp, type PriceRow } from "../api";

const { Text } = Typography;

export function DataStatus() {
  const [health, setHealth] = useState<HealthResp | null>(null);
  const [security, setSecurity] = useState("600519.XSHG");
  const [rows, setRows] = useState<PriceRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onHealth = () => {
    setError(null);
    getHealth()
      .then(setHealth)
      .catch((e) => setError(String(e)));
  };

  const onQuery = () => {
    setLoading(true);
    setError(null);
    getPrice({ security, start_date: "2023-01-03", end_date: "2023-03-31", fields: "open,high,low,close,volume", count: 30 })
      .then((r) => setRows(r.rows.slice(-20)))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  const env = (health?.environment ?? {}) as import("../api").Environment;

  return (
    <div>
      <Card size="small" title="数据源状态 / 审计环境" style={{ marginBottom: 12 }}>
        <Row gutter={12} align="middle">
          <Col flex="auto">
            <Descriptions size="small" column={2} bordered>
              <Descriptions.Item label="连接状态">{health ? <Text type="success">已连接</Text> : <Text type="warning">未连接</Text>}</Descriptions.Item>
              <Descriptions.Item label="Provider">{health?.provider ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="Dolt commit"><Text copyable>{env.dolt_commit ?? "-"}</Text></Descriptions.Item>
              <Descriptions.Item label="Schema 哈希"><Text copyable>{env.schema_hash ?? "-"}</Text></Descriptions.Item>
              <Descriptions.Item label="Provider 版本">{env.provider_version ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="BulletTrade">{env.bullettrade_commit ?? "-"}</Descriptions.Item>
              <Descriptions.Item label="QuantRadar commit"><Text copyable>{env.quantradar_commit ?? "-"}</Text></Descriptions.Item>
            </Descriptions>
          </Col>
          <Col>
            <Button type="primary" onClick={onHealth}>刷新状态</Button>
          </Col>
        </Row>
        {!health && !error && (
          <Button style={{ marginTop: 12 }} onClick={onHealth}>连接数据源</Button>
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
            <Button type="primary" loading={loading} onClick={onQuery}>查询近期行情</Button>
          </Col>
        </Row>
        {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
        {loading && <Spin />}
        {rows.length > 0 && (
          <Table<PriceRow>
            size="small"
            rowKey="date"
            pagination={false}
            dataSource={rows}
            scroll={{ x: "max-content" }}
            columns={[
              { title: "日期", dataIndex: "date" },
              { title: "开盘", dataIndex: "open", render: (v) => (v == null ? "-" : Number(v).toFixed(2)) },
              { title: "最高", dataIndex: "high", render: (v) => (v == null ? "-" : Number(v).toFixed(2)) },
              { title: "最低", dataIndex: "low", render: (v) => (v == null ? "-" : Number(v).toFixed(2)) },
              { title: "收盘", dataIndex: "close", render: (v) => (v == null ? "-" : Number(v).toFixed(2)) },
              { title: "成交量", dataIndex: "volume", render: (v) => (v == null ? "-" : Number(v).toLocaleString("zh-CN")) },
            ]}
          />
        )}
      </Card>
    </div>
  );
}
