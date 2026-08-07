import { useMemo } from "react";
import { Card, Col, Descriptions, Empty, Row, Statistic, Table, Tag, Typography } from "antd";
import ReactECharts from "echarts-for-react";
import type { Environment, Snapshot } from "../api";

const { Text } = Typography;

function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "-";
  return `${(v * 100).toFixed(digits)}%`;
}

function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return "-";
  return v.toLocaleString("zh-CN", { maximumFractionDigits: digits });
}

export function ResultsView({ snapshot }: { snapshot: Snapshot | null | undefined }) {
  const daily = snapshot?.daily_records ?? [];
  const trades = snapshot?.trades ?? [];
  const positions = snapshot?.positions ?? [];

  const { navOption, retOption, ddOption } = useMemo(() => {
    const dates = daily.map((d) => (d.date || "").slice(0, 10));
    const nav = daily.map((d) => d.total_value ?? null);
    const base = nav.find((v) => v != null) ?? 0;
    const cumRet = nav.map((v) => (v != null && base ? (v / base - 1) * 100 : null));
    let peak = -Infinity;
    const drawdown = nav.map((v) => {
      if (v == null) return null;
      peak = Math.max(peak, v);
      return peak ? (v - peak) / peak * 100 : 0;
    });
    const baseOpt = {
      grid: { left: 56, right: 16, top: 24, bottom: 28 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: dates, axisLabel: { fontSize: 10 } },
      yAxis: { type: "value", scale: true, axisLabel: { fontSize: 10 } },
    };
    return {
      navOption: { ...baseOpt, series: [{ name: "净值(元)", type: "line", showSymbol: false, data: nav, areaStyle: { opacity: 0.15 } }] },
      retOption: { ...baseOpt, series: [{ name: "累计收益率(%)", type: "line", showSymbol: false, data: cumRet, lineStyle: { color: "#16a34a" }, itemStyle: { color: "#16a34a" } }] },
      ddOption: { ...baseOpt, series: [{ name: "回撤(%)", type: "line", showSymbol: false, data: drawdown, lineStyle: { color: "#dc2626" }, itemStyle: { color: "#dc2626" }, areaStyle: { opacity: 0.15, color: "#dc2626" } }] },
    };
  }, [daily]);

  if (!snapshot) {
    return <Empty description="暂无回测结果" />;
  }

  const m = snapshot.metrics ?? {};
  const env = (snapshot.environment ?? {}) as Environment;
  const cfg = snapshot.config ?? {};

  return (
    <div>
      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col span={6}><Card size="small"><Statistic title="期末市值" value={fmtNum(m.final_total_value)} valueStyle={{ color: "#2563eb" }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="总收益率" value={fmtPct(m.total_return)} valueStyle={{ color: (m.total_return ?? 0) >= 0 ? "#16a34a" : "#dc2626" }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="最大回撤" value={fmtPct(m.max_drawdown)} valueStyle={{ color: "#dc2626" }} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="交易日数" value={m.days ?? "-"} /></Card></Col>
      </Row>

      <Card size="small" title="净值曲线" style={{ marginBottom: 12 }}>
        <ReactECharts option={navOption} style={{ height: 240 }} notMerge />
      </Card>
      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col span={12}><Card size="small" title="累计收益率"><ReactECharts option={retOption} style={{ height: 200 }} notMerge /></Card></Col>
        <Col span={12}><Card size="small" title="回撤"><ReactECharts option={ddOption} style={{ height: 200 }} notMerge /></Card></Col>
      </Row>

      <Card size="small" title="指标 Metrics" style={{ marginBottom: 12 }}>
        <Descriptions size="small" column={3} bordered>
          <Descriptions.Item label="期末市值">{fmtNum(m.final_total_value)}</Descriptions.Item>
          <Descriptions.Item label="总收益率">{fmtPct(m.total_return)}</Descriptions.Item>
          <Descriptions.Item label="最大回撤">{fmtPct(m.max_drawdown)}</Descriptions.Item>
          <Descriptions.Item label="交易日数">{m.days}</Descriptions.Item>
          <Descriptions.Item label="数据 as-of">{snapshot.data_asof ?? "-"}</Descriptions.Item>
          <Descriptions.Item label="记录数">{snapshot.records_count}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Row gutter={12} style={{ marginBottom: 12 }}>
        <Col span={12}>
          <Card size="small" title="持仓 Positions" style={{ marginBottom: 12 }}>
            <Table<typeof positions[number]>
              size="small"
              rowKey="security"
              pagination={false}
              dataSource={positions}
              columns={[
                { title: "标的", dataIndex: "security" },
                { title: "数量", dataIndex: "amount", render: (v) => fmtNum(v, 0) },
                { title: "成本价", dataIndex: "avg_cost", render: (v) => fmtNum(v) },
                { title: "现价", dataIndex: "price", render: (v) => fmtNum(v) },
                { title: "市值", dataIndex: "value", render: (v) => fmtNum(v) },
              ]}
            />
          </Card>
          <Card size="small" title="成交 Trades">
            <Table<typeof trades[number]>
              size="small"
              rowKey={(r, i) => `${r.time ?? i}`}
              pagination={{ pageSize: 8 }}
              dataSource={trades}
              columns={[
                { title: "时间", dataIndex: "time" },
                { title: "标的", dataIndex: "security" },
                { title: "方向", dataIndex: "action", render: (a) => <Tag color={a === "SELL" ? "red" : "green"}>{a ?? "-"}</Tag> },
                { title: "数量", dataIndex: "amount", render: (v) => fmtNum(v, 0) },
                { title: "价格", dataIndex: "price", render: (v) => fmtNum(v) },
                { title: "手续费", dataIndex: "commission", render: (v) => fmtNum(v) },
              ]}
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title="运行日志 / 每日权益流水" style={{ height: "100%" }}>
            <Table<typeof daily[number]>
              size="small"
              rowKey="date"
              pagination={{ pageSize: 12 }}
              dataSource={daily}
              columns={[
                { title: "日期", dataIndex: "date", render: (d: string) => (d || "").slice(0, 10) },
                { title: "市值", dataIndex: "total_value", render: (v) => fmtNum(v) },
                { title: "现金", dataIndex: "cash", render: (v) => fmtNum(v) },
                { title: "持仓市值", dataIndex: "positions_value", render: (v) => fmtNum(v) },
                { title: "当日收益%", dataIndex: "returns_pct", render: (v) => fmtPct(v) },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Card size="small" title="审计环境 Audit Environment">
        <Descriptions size="small" column={2} bordered>
          <Descriptions.Item label="数据来源">{env.provider}</Descriptions.Item>
          <Descriptions.Item label="Provider 版本">{env.provider_version}</Descriptions.Item>
          <Descriptions.Item label="Dolt commit"><Text copyable>{env.dolt_commit ?? "-"}</Text></Descriptions.Item>
          <Descriptions.Item label="Schema 哈希"><Text copyable>{env.schema_hash ?? "-"}</Text></Descriptions.Item>
          <Descriptions.Item label="BulletTrade commit">{env.bullettrade_commit}</Descriptions.Item>
          <Descriptions.Item label="QuantRadar commit"><Text copyable>{env.quantradar_commit}</Text></Descriptions.Item>
          <Descriptions.Item label="配置哈希"><Text copyable>{snapshot.config_hash}</Text></Descriptions.Item>
          <Descriptions.Item label="策略哈希"><Text copyable>{snapshot.strategy_hash}</Text></Descriptions.Item>
        </Descriptions>
        <div className="muted" style={{ marginTop: 8 }}>
          起始 {String(cfg.start_date ?? "-")} → 结束 {String(cfg.end_date ?? "-")} · 初始资金 {fmtNum(Number(cfg.initial_cash ?? 0), 0)} · 频率 {String(cfg.frequency ?? "-")} · 结果哈希 <Text copyable>{snapshot.result_hash}</Text>
        </div>
      </Card>
    </div>
  );
}
