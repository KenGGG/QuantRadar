import { useState } from "react";
import dayjs from "dayjs";
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Input,
  InputNumber,
  Radio,
  Row,
  Space,
  Spin,
  Typography,
} from "antd";
import Editor from "@monaco-editor/react";
import { runBacktest, runStrategy, type BacktestResp, type Snapshot } from "../api";
import { ResultsView } from "./ResultsView";

const { Text } = Typography;

const SAMPLE = `def initialize(context):
    # 在此注入的全局：get_price / order_target / log / g / run_daily ...
    context.security = '600519.XSHG'
    context.amount = 100

def handle_data(context, data):
    # 每个交易日调用；仅可使用当前日及之前的数据（防未来函数）
    if not context.portfolio.positions:
        order_target(context.security, context.amount)
`;

export function StrategyWorkbench() {
  const [mode, setMode] = useState<"builtin" | "user">("builtin");
  const [code, setCode] = useState(SAMPLE);
  const [security, setSecurity] = useState("600519.XSHG");
  const [start, setStart] = useState("2023-01-03");
  const [end, setEnd] = useState("2023-03-31");
  const [cash, setCash] = useState(500000);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Snapshot | null>(null);

  const onRun = () => {
    setLoading(true);
    setError(null);
    setResult(null);
    const payload = {
      start_date: start,
      end_date: end,
      initial_cash: cash,
      frequency: "day",
    };
    const call = mode === "user"
      ? runStrategy({ ...payload, code })
      : runBacktest({ ...payload, security });
    call
      .then((r: BacktestResp) => setResult(r.snapshot))
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  return (
    <Row gutter={12}>
      <Col xs={24} lg={11}>
        <Card size="small" title="策略编辑器（JoinQuant 兼容）" style={{ marginBottom: 12 }}>
          <Space style={{ marginBottom: 8 }}>
            <Radio.Group
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              optionType="button"
              buttonStyle="solid"
              options={[
                { label: "内置 Buy&Hold", value: "builtin" },
                { label: "自定义源码", value: "user" },
              ]}
            />
          </Space>
          <div style={{ border: "1px solid #d9d9d9", borderRadius: 6, overflow: "hidden" }}>
            <Editor
              height="360px"
              defaultLanguage="python"
              theme="vs-dark"
              value={code}
              onChange={(v) => setCode(v ?? "")}
              options={{ minimap: { enabled: false }, fontSize: 13 }}
            />
          </div>
        </Card>
        <Card size="small" title="回测参数">
          <Row gutter={8} align="middle">
            <Col>
              <Text type="secondary">标的</Text>
              <Input
                value={security}
                onChange={(e) => setSecurity(e.target.value)}
                style={{ width: 180, marginLeft: 8 }}
                disabled={mode === "user"}
              />
            </Col>
            <Col>
              <Text type="secondary" style={{ marginLeft: 8 }}>起</Text>
              <DatePicker value={start ? dayjs(start) : null} onChange={(d) => setStart(d ? d.format("YYYY-MM-DD") : "")} style={{ marginLeft: 4 }} />
            </Col>
            <Col>
              <Text type="secondary" style={{ marginLeft: 8 }}>止</Text>
              <DatePicker value={end ? dayjs(end) : null} onChange={(d) => setEnd(d ? d.format("YYYY-MM-DD") : "")} style={{ marginLeft: 4 }} />
            </Col>
            <Col>
              <Text type="secondary" style={{ marginLeft: 8 }}>初始资金</Text>
              <InputNumber value={cash} min={10000} step={10000} onChange={(v) => setCash(v ?? 500000)} style={{ marginLeft: 4 }} />
            </Col>
          </Row>
          <Button type="primary" loading={loading} onClick={onRun} style={{ marginTop: 12 }}>
            {mode === "user" ? "运行策略回测" : "运行 Buy&Hold 回测"}
          </Button>
          {error && <Alert type="error" showIcon message={error} style={{ marginTop: 12 }} />}
        </Card>
      </Col>
      <Col xs={24} lg={13}>
        <Card size="small" title="回测结果">
          {loading && <div style={{ textAlign: "center", padding: 40 }}><Spin tip="回测执行中（真实数据）..." /></div>}
          {!loading && <ResultsView snapshot={result} />}
        </Card>
      </Col>
    </Row>
  );
}
