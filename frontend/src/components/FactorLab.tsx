import { useEffect, useState } from "react";
import { Alert, Card, Table } from "antd";
import { getFactorCatalog, type FactorCatalogRow } from "../api";

export function FactorLab() {
  const [rows, setRows] = useState<FactorCatalogRow[]>([]); const [error, setError] = useState("");
  useEffect(() => { getFactorCatalog().then(r => setRows(r.factors)).catch(e => setError(String(e))); }, []);
  const ready = rows.filter(r => r.group === "price_volume");
  return <Card title="FactorLab" extra={<span>RAW 工程研究 · 非严格 PIT</span>}>
    {error && <Alert type="error" message={error} showIcon />}
    <p>共 {rows.length} 个 Alpha101 公式；默认可选择 {ready.length} 个量价项。输入 READY、完成计算与完成评价分别记录。</p>
    <Table size="small" pagination={{ pageSize: 12 }} rowKey="alpha_id" dataSource={rows} columns={[
      { title: "编号", dataIndex: "alpha_id" }, { title: "依赖组", dataIndex: "group" }, { title: "预热", dataIndex: "lookback_days" },
      { title: "输入资格", render: (_, r) => r.group === "price_volume" ? "READY" : "PARTIAL" }, { title: "评价", dataIndex: "evaluation_status" },
      { title: "公式", dataIndex: "formula", ellipsis: true },
    ]} />
  </Card>;
}
