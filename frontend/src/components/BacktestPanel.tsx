import { useState } from "react";
import { runBacktest, saveSnapshot, type BacktestSummary, type Snapshot } from "../api";

export function BacktestPanel() {
  const [security, setSecurity] = useState("600519.XSHG");
  const [startDate, setStartDate] = useState("2023-01-01");
  const [endDate, setEndDate] = useState("2023-03-31");
  const [initialCash, setInitialCash] = useState(500000);
  const [amount, setAmount] = useState(100);
  const [summary, setSummary] = useState<BacktestSummary | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedPath, setSavedPath] = useState<string | null>(null);

  async function onRun() {
    setLoading(true);
    setError(null);
    setSavedPath(null);
    try {
      const resp = await runBacktest({
        security,
        start_date: startDate || null,
        end_date: endDate || null,
        initial_cash: initialCash,
        amount,
      });
      setSummary(resp.summary);
      setSnapshot(resp.snapshot);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setSummary(null);
      setSnapshot(null);
    } finally {
      setLoading(false);
    }
  }

  async function onSave() {
    if (!snapshot) return;
    try {
      const resp = await saveSnapshot({ snapshot, name: snapshot.result_fingerprint });
      setSavedPath(resp.path);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section>
      <h2>真实回测（Buy &amp; Hold）</h2>
      <div className="row">
        <label>
          代码
          <input value={security} onChange={(e) => setSecurity(e.target.value)} />
        </label>
        <label>
          开始
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </label>
        <label>
          结束
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </label>
        <label>
          初始资金
          <input type="number" value={initialCash} onChange={(e) => setInitialCash(Number(e.target.value))} />
        </label>
        <label>
          股数
          <input type="number" value={amount} onChange={(e) => setAmount(Number(e.target.value))} />
        </label>
        <button onClick={onRun} disabled={loading}>
          {loading ? "回测中…" : "运行回测"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {summary && (
        <div className="result">
          <h3>回测摘要</h3>
          <ul>
            <li>代码：{summary.security}</li>
            <li>区间：{summary.start_date} ~ {summary.end_date}</li>
            <li>交易日数：{summary.records_count}</li>
            <li>期末总值：{summary.final_total_value}</li>
          </ul>
          {snapshot && (
            <>
              <p>快照指纹：{snapshot.result_fingerprint}（asof {snapshot.asof}）</p>
              <button onClick={onSave}>保存快照</button>
              {savedPath && <p className="ok">已保存：{savedPath}</p>}
            </>
          )}
        </div>
      )}
    </section>
  );
}
