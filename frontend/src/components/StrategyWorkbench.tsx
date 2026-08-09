import { useCallback, useEffect, useRef, useState } from "react";
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
  Select,
  Space,
  Spin,
  Typography,
} from "antd";
import Editor from "@monaco-editor/react";
import {
  submitAsync,
  getRun,
  type RunRecord,
  type BacktestPayload,
} from "../api";

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

const FQ_OPTIONS = [
  { label: "原始价(none)", value: "none" },
  { label: "前复权(pre)", value: "pre" },
  { label: "前复权(qfq)", value: "qfq" },
  { label: "后复权(post)", value: "post" },
  { label: "后复权(hfq)", value: "hfq" },
];

export function StrategyWorkbench({
  onOpenReport,
}: {
  onOpenReport: (runId: string) => void;
}) {
  const [mode, setMode] = useState<"builtin" | "user">("user");
  const [code, setCode] = useState(SAMPLE);
  const [security, setSecurity] = useState("600519.XSHG");
  const [start, setStart] = useState("2023-01-03");
  const [end, setEnd] = useState("2023-03-31");
  const [cash, setCash] = useState(500000);
  const [benchmark, setBenchmark] = useState("000300.XSHG");
  const [fq, setFq] = useState("none");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<RunRecord | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = () => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  };

  const poll = useCallback(
    (runId: string) => {
      stopPoll();
      timer.current = setInterval(async () => {
        try {
          const rec = await getRun(runId);
          setRun(rec);
          if (rec.status === "SUCCESS" || rec.status === "FAILED") {
            stopPoll();
            setLoading(false);
            if (rec.status === "SUCCESS") onOpenReport(runId);
          }
        } catch {
          /* 瞬时错误忽略，继续轮询 */
        }
      }, 1500);
    },
    [onOpenReport]
  );

  const onRun = () => {
    setLoading(true);
    setError(null);
    setRun(null);
    const base: BacktestPayload = {
      start_date: start,
      end_date: end,
      initial_cash: cash,
      frequency: "day",
      benchmark: benchmark || null,
      fq,
      strategy_name: "web_strategy",
    };
    const payload: BacktestPayload =
      mode === "user" ? { ...base, code } : { ...base, security };
    submitAsync(payload)
      .then((r) => {
        setRun({ run_id: r.run_id, status: "PENDING", config: r.config });
        poll(r.run_id);
      })
      .catch((e: unknown) => {
        setError(String(e));
        setLoading(false);
      });
  };

  // 组件卸载时停止轮询
  useEffect(() => stopPoll, []);

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
              height="340px"
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
                style={{ width: 170, marginLeft: 8 }}
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
          </Row>
          <Row gutter={8} align="middle" style={{ marginTop: 8 }}>
            <Col>
              <Text type="secondary">初始资金</Text>
              <InputNumber value={cash} min={10000} step={10000} onChange={(v) => setCash(v ?? 500000)} style={{ marginLeft: 4, width: 130 }} />
            </Col>
            <Col>
              <Text type="secondary" style={{ marginLeft: 8 }}>Benchmark</Text>
              <Input value={benchmark} onChange={(e) => setBenchmark(e.target.value)} placeholder="000300.XSHG" style={{ width: 140, marginLeft: 4 }} />
            </Col>
            <Col>
              <Text type="secondary" style={{ marginLeft: 8 }}>复权</Text>
              <Select value={fq} onChange={setFq} options={FQ_OPTIONS} style={{ width: 130, marginLeft: 4 }} />
            </Col>
          </Row>
          <Button type="primary" loading={loading} onClick={onRun} style={{ marginTop: 12 }}>
            {mode === "user" ? "运行策略回测" : "运行 Buy&Hold 回测"}
          </Button>
        </Card>
      </Col>
      <Col xs={24} lg={13}>
        <Card size="small" title="提交状态">
          {loading && (
            <div style={{ textAlign: "center", padding: 40 }}>
              <Spin tip="后台回测执行中（真实数据，复用 BulletTrade 原生报告）..." />
            </div>
          )}
          {!loading && !run && <Text type="secondary">填写策略与参数后点击运行；完成后自动跳转到完整回测报告页。</Text>}
          {!loading && run && (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Text>run_id：<Text copyable>{run.run_id}</Text></Text>
              <Text>状态：{run.status}</Text>
              {run.status === "SUCCESS" && (
                <Button type="link" onClick={() => onOpenReport(run.run_id)}>
                  打开完整回测报告 →
                </Button>
              )}
              {run.status === "FAILED" && run.error && (
                <Alert type="error" showIcon message="回测失败" description={<pre style={{ whiteSpace: "pre-wrap", margin: 0 }}>{run.error}</pre>} />
              )}
            </Space>
          )}
          {error && <Alert type="error" showIcon message={error} style={{ marginTop: 12 }} />}
        </Card>
      </Col>
    </Row>
  );
}
