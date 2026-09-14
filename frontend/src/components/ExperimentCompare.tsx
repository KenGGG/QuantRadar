import { useCallback, useEffect, useState } from "react";
import { Alert, Card, Checkbox, Empty, Spin, Table } from "antd";
import ReactECharts from "echarts-for-react";
import { listExperiments, getExperiment, type ExperimentResp } from "../api";

export function ExperimentCompare() {
  const [experiments, setExperiments] = useState<ExperimentResp[]>([]);
  const [checked, setChecked] = useState<string[]>([]);
  const [exps, setExps] = useState<Record<string, ExperimentResp>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    setError(null);
    listExperiments()
      .then((r) => {
        setExperiments(r.experiments);
        if (r.experiments.length && checked.length === 0) {
          setChecked(r.experiments.slice(0, 2).map(e => e.experiment_id));
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
        } catch (e) {
          out[n] = { experiment_id: n, display_name: n, kind: "unavailable", error: String(e) };
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
        name: exps[n]?.display_name || n,
        type: "line",
        showSymbol: false,
        data: daily.map((d) => {
          const initialCash = Number((exps[n]?.snapshot?.config || exps[n]?.config || {}).initial_cash || 0);
          return [String(d.date).slice(0, 10), initialCash > 0 && d.total_value != null ? d.total_value / initialCash : null];
        }),
      });
    }
    const dates = Array.from(allDates).sort();
    return {
      tooltip: { trigger: "axis" },
      legend: { data: checked.map(id => exps[id]?.display_name || id) },
      grid: { left: 64, right: 16, top: 32, bottom: 28 },
      xAxis: { type: "category", data: dates },
      yAxis: { type: "value", scale: true, axisLabel: { formatter: (v: number) => v.toFixed(2) } },
      series,
    };
  })();

  return (
    <Card size="small" title="实验对比（基于 Snapshot 指纹的本地实验存证）">
      {loading && <Spin />}
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
      {!experiments.length && !loading && <Empty description="暂无实验；请从成功的运行记录保存实验" />}
      {experiments.length > 0 && (
        <>
          <Checkbox.Group
            options={experiments.map((e) => ({ label: `${e.display_name}${e.legacy ? "（旧存证）" : ""}`, value: e.experiment_id }))}
            value={checked}
            onChange={(v) => setChecked(v as string[])}
            style={{ marginBottom: 12 }}
          />
          <div className="muted" style={{ marginBottom: 8 }}>
            选中 {checked.length} 个实验，下方以 portfolio_value / initial_cash 叠加净值；每条曲线保留自己的日期轴与缺口。
          </div>
          {checked.length === 0 ? (
            <Empty description="请至少选择一个实验" />
          ) : (
            <ReactECharts option={option} style={{ height: 360 }} notMerge />
          )}
          <Table size="small" pagination={false} style={{ marginTop: 16 }} rowKey="experiment_id"
            dataSource={checked.map(id => exps[id]).filter(Boolean)}
            columns={[{ title: "实验", dataIndex: "display_name" }, { title: "状态", render: (_, row) => row.error ? <span className="error">{String(row.error)}</span> : row.legacy ? "旧存证：版本未知" : "可复现" }, { title: "版本", render: (_, row) => String((row.config || {}).release_id || "未记录") }, { title: "对象池", render: (_, row) => String((row.config || {}).pool_type || (row.config || {}).security || "未记录") }, { title: "模式", render: (_, row) => String((row.config || {}).fq || (row.config || {}).price_mode || "未记录") }, { title: "基准", render: (_, row) => String((row.config || {}).benchmark || "无") }]} />
        </>
      )}
    </Card>
  );
}
