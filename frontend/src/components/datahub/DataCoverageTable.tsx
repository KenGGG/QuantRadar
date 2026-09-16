import { Card, Table, Tooltip } from 'antd';

type Row = {
  key: string;
  name: string;
  published?: { stocks?: number; first_date?: string; latest_date?: string; qualification?: string };
  usage: string;
  qualification: string;
  researchLabel?: string;
  researchTooltip?: string;
};
const qualification = (value: string) => value.includes('RAW_RESEARCH') ? '可用于一般研究' : value.includes('PIT') ? '严格历史时点未验证' : value.includes('PARTIAL') ? '部分覆盖' : value.includes('READABLE') ? '数据存在' : '未提供';
const fmt = (value: number | undefined) => value == null ? '未提供' : value.toLocaleString();

export function DataCoverageTable({ rows }: { rows: Row[] }) {
  return <Card title="数据完整度"><Table rowKey="key" pagination={false} size="middle" scroll={{ x: 720 }} dataSource={rows} columns={[
    { title: '数据', dataIndex: 'name' },
    { title: '可用于研究', render: (_, row: Row) => <Tooltip title={row.researchTooltip ?? row.qualification}>{row.researchLabel ?? qualification(row.qualification)}</Tooltip> },
    { title: '股票覆盖', render: (_, row: Row) => fmt(row.published?.stocks) },
    { title: '时间范围', render: (_, row: Row) => row.published?.first_date ? `${row.published.first_date} — ${row.published.latest_date ?? '未提供'}` : '未提供' },
    { title: '状态', dataIndex: 'usage' },
  ]} /></Card>;
}
