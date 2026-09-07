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
  listStrategies, saveStrategy, type StrategyRecord,
  submitAsync,
  getRun,
  type RunRecord,
  type BacktestPayload,
} from "../api";

const { Text } = Typography;

import { SAMPLES } from "../strategySamples";

const FQ_OPTIONS = [
  { label: "原始价(none)", value: "none" },
  { label: "前复权(pre)", value: "pre" },
];

export function StrategyWorkbench({
  onOpenReport, restoreRun,
}: {
  onOpenReport: (runId: string) => void;
  restoreRun: RunRecord | null;
}) {
  const [mode, setMode] = useState<"builtin" | "user">("user");
  const [code, setCode] = useState(SAMPLES.buyhold.source);
  const [name, setName] = useState("买入持有");
  const [strategies, setStrategies] = useState<StrategyRecord[]>([]);
  const [saved, setSaved] = useState("");
  const [saving, setSaving] = useState(false);
  const [amount, setAmount] = useState(100);
  const [extras, setExtras] = useState<Record<string, unknown> | null>(null);
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

  useEffect(() => { listStrategies().then(r => setStrategies(r.strategies)).catch(e => setError(String(e))); }, []);
  useEffect(() => {
    if (!restoreRun) return;
    const cfg = restoreRun.config || {};
    if (cfg.has_code && !cfg.strategy_source) { setError("历史源码缺失，无法恢复"); return; }
    setMode(cfg.has_code ? "user" : "builtin");
    if (cfg.strategy_source) setCode(String(cfg.strategy_source));
    setName(String(cfg.strategy_name || "历史策略"));
    setSecurity(String(cfg.security || "600519.XSHG"));
    setStart(String(cfg.start_date || "")); setEnd(String(cfg.end_date || ""));
    setCash(Number(cfg.initial_cash)); setAmount(Number(cfg.amount || 100));
    setBenchmark(String(cfg.benchmark || "")); setFq(String(cfg.fq || "none"));
    setExtras((cfg.extras as Record<string, unknown>) || null);
    setSaved(`已恢复历史源码与配置：${restoreRun.run_id}`); setError(null);
  }, [restoreRun]);
  const onSave = async () => {
    setSaving(true); setError(null);
    try {
      const item = await saveStrategy(name, code);
      setStrategies((await listStrategies()).strategies);
      setSaved(`已保存版本 #${item.id}：${item.name}`);
    } catch (e) { setError(String(e)); }
    finally { setSaving(false); }
  };

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

          }
        } catch (e) {
          setError(`状态查询失败，将继续重试：${String(e)}`);
        }
      }, 1500);
    },
    [onOpenReport]
  );

  const onRun = () => {
    if (!start || !end || start > end || cash <= 0) { setError("请填写有效日期区间与初始资金"); return; }
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
      strategy_name: name, amount, extras,
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
          <Space wrap style={{ marginBottom: 8 }}>
            <Input aria-label="策略名称" value={name} onChange={e => setName(e.target.value)} style={{ width: 170 }} />
            <Button onClick={onSave} loading={saving} disabled={mode !== "user"}>保存策略版本</Button>
            <select aria-label="打开策略版本" value="" onChange={e => {
              const item = strategies.find(s => s.id === Number(e.target.value));
              if (item) { setCode(item.source); setName(item.name); setMode("user"); setSaved(`已打开版本 #${item.id}`); }
            }}>
              <option value="">打开已保存策略…</option>
              {strategies.map(s => <option key={s.id} value={s.id}>{s.name} · #{s.id}</option>)}
            </select>
            <select aria-label="载入样例" value="" onChange={e => {
              const sample = SAMPLES[e.target.value as keyof typeof SAMPLES];
              if (sample) { setCode(sample.source); setName(sample.name); setMode("user"); setSaved(""); }
            }}>
              <option value="">载入样例…</option>
              {Object.entries(SAMPLES).map(([key, s]) => <option key={key} value={key}>{s.name}</option>)}
            </select>
          </Space>
          {saved && <Alert type="success" message={saved} style={{ marginBottom: 8 }} />}
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
          {mode === "builtin" && <Text type="secondary">内置模式按下方标的与目标股数生成策略；此处源码只用于自定义模式。</Text>}
          <div style={{ border: "1px solid #d9d9d9", borderRadius: 6, overflow: "hidden" }}>
            <Editor
              height="340px"
              defaultLanguage="python"
              theme="vs-dark"
              value={code}
              onChange={(v) => setCode(v ?? "")}
              options={{ readOnly: mode === "builtin", minimap: { enabled: false }, fontSize: 13 }}
            />
          </div>
        </Card>
        <Card size="small" title="回测参数">
          <Row gutter={8} align="middle">
            <Col>
              <Text type="secondary">标的</Text>
              <Input
                aria-label="标的" value={security}
                onChange={(e) => setSecurity(e.target.value)}
                style={{ width: 170, marginLeft: 8 }}
                disabled={mode === "user"}
              />
            </Col>
            <Col>
              <Text type="secondary" style={{ marginLeft: 8 }}>起</Text>
              <DatePicker aria-label="起始日期" value={start ? dayjs(start) : null} onChange={(d) => setStart(d ? d.format("YYYY-MM-DD") : "")} style={{ marginLeft: 4 }} />
            </Col>
            <Col>
              <Text type="secondary" style={{ marginLeft: 8 }}>止</Text>
              <DatePicker aria-label="结束日期" value={end ? dayjs(end) : null} onChange={(d) => setEnd(d ? d.format("YYYY-MM-DD") : "")} style={{ marginLeft: 4 }} />
            </Col>
          </Row>
          <Row gutter={8} align="middle" style={{ marginTop: 8 }}>
            <Col>
              <Text type="secondary">初始资金</Text>
              <InputNumber aria-label="初始资金" value={cash} min={10000} step={10000} onChange={(v) => setCash(v ?? 500000)} style={{ marginLeft: 4, width: 130 }} />
            </Col>
            <Col>
              <Text type="secondary" style={{ marginLeft: 8 }}>Benchmark</Text>
              <Input aria-label="基准" value={benchmark} onChange={(e) => setBenchmark(e.target.value)} placeholder="000300.XSHG" style={{ width: 140, marginLeft: 4 }} />
            </Col>
            <Col>
              <Text type="secondary" style={{ marginLeft: 8 }}>复权</Text>
              <Select value={fq} onChange={setFq} options={FQ_OPTIONS} style={{ width: 130, marginLeft: 4 }} />
            </Col>
          </Row>
          {mode === "builtin" && <div>目标股数 <InputNumber aria-label="目标股数" value={amount} min={100} step={100} onChange={v => setAmount(v || 100)} /></div>}
          <Text type="secondary">日频；复权控制引擎行情口径，策略显式 get_price(fq=…) 以源码为准。源码内 set_benchmark 会覆盖页面基准。</Text>
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
          {!loading && !run && <Text type="secondary">填写策略与参数后点击运行；完成后点击打开完整回测报告，返回可继续编辑。</Text>}
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
