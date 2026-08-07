import { useState } from "react";
import { getPrice, type PriceRow } from "../api";

const COLUMNS = ["open", "high", "low", "close", "volume", "amount"];

export function PriceQuery() {
  const [security, setSecurity] = useState("600519.XSHG");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [count, setCount] = useState(30);
  const [rows, setRows] = useState<PriceRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onQuery() {
    setLoading(true);
    setError(null);
    try {
      const resp = await getPrice({
        security,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        fq: "none",
        fields: COLUMNS.join(","),
        count,
      });
      setRows(resp.rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <h2>行情查询</h2>
      <div className="row">
        <label>
          代码
          <input value={security} onChange={(e) => setSecurity(e.target.value)} placeholder="600519.XSHG" />
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
          条数
          <input
            type="number"
            value={count}
            min={1}
            max={300}
            onChange={(e) => setCount(Number(e.target.value))}
          />
        </label>
        <button onClick={onQuery} disabled={loading}>
          {loading ? "查询中…" : "查询"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {rows.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>日期</th>
              {COLUMNS.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.date}>
                <td>{r.date}</td>
                {COLUMNS.map((c) => (
                  <td key={c}>{r[c] === null ? "-" : String(r[c])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
