import ReactECharts from "echarts-for-react";
import type { NativeReportData } from "../api";

const mainMetrics = ["策略收益", "策略年化收益", "累计超额收益", "基准收益", "夏普比率", "最大回撤"];
const moreMetrics = ["索提诺比率", "盈亏比", "日胜率", "交易胜率", "策略波动率", "基准年化收益", "交易天数", "日盈利天数", "日亏损天数", "交易盈利次数", "交易亏损次数", "最大回撤区间"];
const percent = new Set(["策略收益", "策略年化收益", "累计超额收益", "基准收益", "最大回撤", "日胜率", "交易胜率", "策略波动率", "基准年化收益"]);

export function ReturnOverview({ data, compact = false }: { data: NativeReportData | null; compact?: boolean }) {
  const rows = data?.daily.rows || [];
  const series = [{ name: "策略收益", field: "returns_pct", color: "#4179b5" }, { name: "基准收益", field: "benchmark_returns_pct", color: "#c64c44" }, { name: "超额收益", field: "excess_returns_pct", color: "#e6a05a" }];
  // Plot stored native series verbatim. Unit formatting is presentation only.
  const option = {
    animation: false,
    tooltip: { trigger: "axis", valueFormatter: (v: unknown) => v == null ? "—" : `${Number(v).toFixed(2)}%` },
    legend: { top: 8, left: 20, icon: "rect", itemWidth: 10, itemHeight: 10, textStyle: { color: "#607189", fontSize: 12 } },
    grid: { left: 58, right: 28, top: 48, bottom: 65 },
    xAxis: { type: "category", data: rows.map(r => r.date.slice(0, 10)), boundaryGap: false, axisLine: { lineStyle: { color: "#c4ccd5" } }, axisLabel: { color: "#7d8b9e", fontSize: 11 }, splitLine: { show: true, lineStyle: { color: "#e4e8ec" } } },
    yAxis: { type: "value", axisLabel: { formatter: "{value}%", color: "#7d8b9e" }, splitLine: { lineStyle: { color: "#e4e8ec" } } },
    dataZoom: [{ type: "slider", height: 18, bottom: 12, borderColor: "#cbd4de" }, { type: "inside" }],
    series: series.filter(s => rows.some(r => r[s.field] !== undefined && r[s.field] !== "")).map(s => ({ name: s.name, type: "line", showSymbol: false, connectNulls: false, lineStyle: { width: 1.7 }, itemStyle: { color: s.color }, areaStyle: s.field === "returns_pct" ? { opacity: .12 } : undefined, data: rows.map(r => r[s.field] === "" || r[s.field] == null ? null : Number(r[s.field])) })),
  };
  return <div className={`return-overview ${compact ? "compact" : ""}`}>
    <div className="metrics-grid">{[...mainMetrics, ...(compact ? [] : moreMetrics)].map(key => {
      const value = data?.metrics[key];
      const display = value == null ? "--" : typeof value === "number" ? `${value.toLocaleString("zh-CN", { maximumFractionDigits: percent.has(key) ? 2 : 3 })}${percent.has(key) ? "%" : ""}` : value;
      return <div className={`report-metric ${key === "最大回撤区间" ? "wide" : ""}`} key={key}><span>{key}</span><strong className={key.includes("收益") && typeof value === "number" ? value >= 0 ? "positive" : "negative" : ""}>{display}</strong></div>;
    })}</div>
    <div className="returns-chart">{data && rows.length ? <ReactECharts option={option} style={{ height: "100%", minHeight: compact ? 260 : 310 }} notMerge /> : <div className="chart-empty"><span>收益曲线</span><p>设置回测区间和资金，点击「运行策略回测」查看结果</p></div>}</div>
    {!compact && data && <div className="asset-chart"><div className="panel-heading">每日资产与持仓市值</div><ReactECharts style={{ height: 210 }} option={{ animation: false, tooltip: { trigger: "axis" }, legend: { top: 8 }, grid: { left: 80, right: 28, top: 40, bottom: 28 }, xAxis: { type: "category", data: rows.map(r => r.date.slice(0, 10)), axisLabel: { color: "#7d8b9e" } }, yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: "#e4e8ec" } } }, series: [{ name: "总资产", field: "total_value", color: "#4179b5" }, { name: "持仓市值", field: "positions_value", color: "#28a3b7" }, { name: "可用资金", field: "cash", color: "#a3b371" }].map(s => ({ name: s.name, type: "line", showSymbol: false, itemStyle: { color: s.color }, data: rows.map(r => r[s.field] === "" || r[s.field] == null ? null : Number(r[s.field])) })) }} /></div>}
  </div>;
}
