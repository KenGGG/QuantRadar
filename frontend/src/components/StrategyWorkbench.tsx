import { useCallback, useEffect, useRef, useState } from "react";
import dayjs from "dayjs";
import {
  Alert,
  Button,
  DatePicker,
  Input,
  InputNumber,
  Radio,
  Select,
} from "antd";
import Editor from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import {
  listStrategies, saveStrategy, type StrategyRecord,
  submitAsync,
  getRun,
  type RunRecord,
  type BacktestPayload,
} from "../api";

import { ReturnOverview } from "./ReturnOverview";
import { getRunReportData, getRunArtifactUrl, type NativeReportData } from "../api";

import { SAMPLES } from "../strategySamples";

const FQ_OPTIONS = [
  { label: "原始价(none)", value: "none" },
  { label: "前复权(pre)", value: "pre" },
];

export function StrategyWorkbench({
  onOpenReport, restoreRun, onNameChange, onRunChange,
}: {
  onOpenReport: (runId: string) => void;
  restoreRun: RunRecord | null;
  onNameChange: (name: string) => void;
  onRunChange: (runId: string) => void;
}) {
  const [mode, setMode] = useState<"builtin" | "user">("user");
  const codeRef = useRef(SAMPLES.buyhold.source);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const setCode = (source: string) => {
    codeRef.current = source;
    editorRef.current?.setValue(source);
  };
  const currentCode = () => editorRef.current?.getValue() ?? codeRef.current;
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
  const [data, setData] = useState<NativeReportData | null>(null);
  const [log, setLog] = useState("");
  const [consoleTab, setConsoleTab] = useState("log");
  useEffect(() => { onNameChange(name); }, [name, onNameChange]);
  useEffect(() => {
    setData(null); setLog("");
    if (!run) return;
    onRunChange(run.run_id);
    if (run.status !== "SUCCESS" && run.status !== "FAILED") return;
    let active = true;
    if (run.status === "SUCCESS") getRunReportData(run.run_id).then(d => { if (active) setData(d); }).catch(e => { if (active) setError(String(e)); });
    fetch(getRunArtifactUrl(run.run_id, "backtest.log")).then(async r => {
      if (!r.ok) throw new Error(`日志暂不可用 (${r.status})`);
      return r.text();
    }).then(text => { if (active) setLog(text); }).catch(e => { if (active) setLog(String(e)); });
    return () => { active = false; };
  }, [run?.run_id, run?.status, onRunChange]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollGeneration = useRef(0);

  useEffect(() => { listStrategies().then(r => setStrategies(r.strategies)).catch(e => setError(String(e))); }, []);
  useEffect(() => {
    if (!restoreRun) return;
    stopPoll(); setLoading(false); setRun(restoreRun);
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
    if (["PENDING", "RUNNING"].includes(restoreRun.status)) {
      setLoading(true);
      poll(restoreRun.run_id);
    }
  }, [restoreRun]);
  const onSave = async () => {
    setSaving(true); setError(null);
    try {
      const item = await saveStrategy(name, currentCode());
      setStrategies((await listStrategies()).strategies);
      setSaved(`已保存版本 #${item.id}：${item.name}`);
    } catch (e) { setError(String(e)); }
    finally { setSaving(false); }
  };

  const stopPoll = () => {
    pollGeneration.current += 1;
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  };

  const poll = useCallback(
    (runId: string) => {
      stopPoll();
      const generation = pollGeneration.current;
      timer.current = setInterval(async () => {
        try {
          const rec = await getRun(runId);
          if (generation !== pollGeneration.current) return;
          setRun(rec);
          if (rec.status === "SUCCESS" || rec.status === "FAILED") {
            stopPoll();
            setLoading(false);

          }
        } catch (e) {
          if (generation !== pollGeneration.current) return;
          setError(`状态查询失败，将继续重试：${String(e)}`);
        }
      }, 1500);
    },
    []
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
      mode === "user" ? { ...base, code: currentCode() } : { ...base, security };
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

  return <div className="strategy-workbench">
    <section className="editor-pane" aria-label="策略编辑器">
      <div className="editor-toolbar">
        <Input aria-label="策略名称" value={name} onChange={e => { setName(e.target.value); setSaved(""); }} style={{ width: 155 }} />
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
      </div>
      <div className="editor-mode">
        <Radio.Group size="small" value={mode} onChange={e => setMode(e.target.value)} options={[{ label: "自定义源码", value: "user" }, { label: "内置 Buy&Hold", value: "builtin" }]} />
        <span className="save-state" role="status">{saved || "编辑后请保存版本"}</span>
      </div>
      {mode === "builtin" && <div className="builtin-note">内置模式使用右侧标的和股数生成策略；切换自定义源码可编辑当前代码。</div>}
      <div className="code-editor"><Editor height="100%" defaultLanguage="python" theme="vs-dark" defaultValue={codeRef.current}
        onMount={instance => { editorRef.current = instance; if (instance.getValue() !== codeRef.current) instance.setValue(codeRef.current); }}
        onChange={v => { codeRef.current = v ?? ""; setSaved(""); }}
        options={{ readOnly: mode === "builtin", minimap: { enabled: false }, fontSize: 14, automaticLayout: true, scrollBeyondLastLine: false, padding: { top: 12 } }} /></div>
      <div className="editor-footer"><span>Python3</span><span>UTF-8 · JoinQuant 兼容语法</span></div>
    </section>
    <section className="preview-pane" aria-label="回测工作区">
      <div className="backtest-toolbar">
        <DatePicker aria-label="起始日期" value={start ? dayjs(start) : null} onChange={d => setStart(d ? d.format("YYYY-MM-DD") : "")} />
        <span>至</span>
        <DatePicker aria-label="结束日期" value={end ? dayjs(end) : null} onChange={d => setEnd(d ? d.format("YYYY-MM-DD") : "")} />
        <label className="cash-field">¥ <InputNumber aria-label="初始资金" value={cash} min={1} step={10000} onChange={v => setCash(v ?? 0)} /></label>
        <span className="frequency-label">每天</span>
        <Button type="primary" loading={loading} onClick={onRun}>{mode === "user" ? "运行策略回测" : "运行 Buy&Hold 回测"}</Button>
      </div>
      <div className="secondary-toolbar">
        <label>基准 <Input aria-label="基准" value={benchmark} onChange={e => setBenchmark(e.target.value)} placeholder="不使用基准" /></label>
        <label>复权 <Select aria-label="复权" value={fq} onChange={setFq} options={FQ_OPTIONS} /></label>
        {mode === "builtin" && <><label>标的 <Input aria-label="标的" value={security} onChange={e => setSecurity(e.target.value)} /></label><label>目标股数 <InputNumber aria-label="目标股数" value={amount} min={100} step={100} onChange={v => setAmount(v || 100)} /></label></>}
        <span className="parameter-note" title="策略内 set_benchmark 会覆盖页面基准；显式 get_price(fq=…) 以源码为准。">源码设置优先 ⓘ</span>
      </div>
      <div className="preview-result">
        {error && <Alert type="error" showIcon message={error} closable onClose={() => setError(null)} />}
        {run?.status === "FAILED" && <Alert type="error" showIcon message="回测失败" description={run.error} />}
        <ReturnOverview data={data} compact />
        <div className="run-status" role="status"><span>{loading ? "回测执行中…" : run ? `状态：${run.status} · ${run.run_id}` : "就绪 · 等待运行"}</span>
          {run?.status === "SUCCESS" && <Button type="link" onClick={() => onOpenReport(run.run_id)}>打开完整回测报告 →</Button>}
        </div>
      </div>
      <div className="console-pane">
        <div className="console-tabs"><button className={consoleTab === "log" ? "active" : ""} onClick={() => setConsoleTab("log")}>日志</button><button className={consoleTab === "error" ? "active" : ""} onClick={() => setConsoleTab("error")}>错误{run?.status === "FAILED" ? " · 1" : ""}</button><span>{run ? "本次回测输出" : "运行输出"}</span></div>
        <pre className="console-output">{consoleTab === "error" ? (error || run?.error || "暂无错误") : log || (loading ? "正在执行回测，完成后显示完整日志…" : "等待策略运行…")}</pre>
      </div>
    </section>
  </div>;
}
