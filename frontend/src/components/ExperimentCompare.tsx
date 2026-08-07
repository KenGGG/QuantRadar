import { useCallback, useEffect, useState } from "react";
import { Alert, Card, Checkbox, Empty, Spin } from "antd";
import ReactECharts from "echarts-for-react";
import { listExperiments, getExperiment, type ExperimentResp } from "../api";

export function ExperimentCompare() {
  const [names, setNames] = useState<string[]>([]);
  const [checked, setChecked] = useState<string[]>([]);
  const [exps, setExps] = useState<Record<string, ExperimentResp>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    listExperiments()
      .then((r) => {
        setNames(r.experiments);
        if (r.experiments.length && checked.length === 0) {
          setChecked(r.experiments.slice(0, 2));
        }
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [checked.length]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    let alive = true;
    (async () => {
      const out: Record<string, ExperimentResp> = {};
      for (const n of checked) {
        try {
          out[n] = await getExperiment(n);
        } catch {
          /* skip missing */
        }
      }
      if (alive) setExps(out);
    })();
    return () => {
      alive = false;
    };
  }, [checked]);

  const option = (() => {
    const series: unknown[] = [];
    const allDates = new Set<string>();
    for (const n of checked) {
      const daily = exps[n]?.snapshot?.daily_records ?? [];
      daily.forEach((d) => d.date && allDates.add(String(d.date).slice(0, 10)));
      series.push({
        name: n,
        type: "line",
        showSymbol: false,
        data: daily.map((d) => [String(d.date).slice(0, 10), d.total_value ?? null]),
      });
    }
    const dates = Array.from(allDates).sort();
    return {
      tooltip: { trigger: "axis" },
      legend: { data: checked },
      grid: { left: 64, right: 16, top: 32, bottom: 28 },
      xAxis: { type: "category", data: dates },
      yAxis: { type: "value", scale: true },
      series,
    };
  })();

  return (
    <Card size="small" title="实验对比（基于 Snapshot 指纹的本地实验存证）">
      {loading && <Spin />}
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
      {!names.length && !loading && <Empty description="暂无实验；可在策略回测后通过 /api/experiments/save 保存" />}
      {names.length > 0 && (
        <>
          <Checkbox.Group
            options={names.map((n) => ({ label: n, value: n }))}
            value={checked}
            onChange={(v) => setChecked(v as string[])}
            style={{ marginBottom: 12 }}
          />
          <div className="muted" style={{ marginBottom: 8 }}>
            选中 {checked.length} 个实验，下方叠加净值曲线对比（数据区间以各自 Snapshot 为准）。
          </div>
          {checked.length === 0 ? (
            <Empty description="请至少选择一个实验" />
          ) : (
            <ReactECharts option={option} style={{ height: 360 }} notMerge />
          )}
        </>
      )}
    </Card>
  );
}
