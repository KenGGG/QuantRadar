import { Button, Card, Space, Tag, Typography } from 'antd';
import type { CollectorProcess } from './DataCollectorProcess';

const fmt = (value: number | null | undefined) => value == null ? '未提供' : value.toLocaleString();
const time = (value: string | null | undefined) => value ? new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '未提供';

export function DataActivitySummary({ collectors, releaseId, onRefresh }: { collectors: CollectorProcess[]; releaseId?: string; onRefresh: () => void }) {
  const running = collectors.filter(item => item.status === 'RUNNING');
  const endpoints = new Set(running.map(item => item.adapter ?? item.endpoint).filter(Boolean)).size;
  const pending = collectors.reduce((sum, item) => sum + item.pending, 0);
  const heartbeats = collectors.map(item => item.heartbeat).filter((item): item is string => Boolean(item)).sort();
  const heartbeat = heartbeats[heartbeats.length - 1];
  return <Card title="后台运行概览" extra={<Button onClick={onRefresh}>立即刷新</Button>}>
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Space><Tag color={running.length ? 'processing' : 'default'}>{running.length ? '数据维护进行中' : '当前无运行任务'}</Tag>{running.length ? <Typography.Text type="secondary">自动刷新中 · 4秒</Typography.Text> : <Typography.Text type="secondary">自动刷新已停止</Typography.Text>}</Space>
      <Space wrap size="large"><Typography.Text>运行中进程 <b>{fmt(running.length)}</b></Typography.Text><Typography.Text>正在调用接口 <b>{fmt(endpoints)}</b></Typography.Text><Typography.Text>后台待处理 <b>{fmt(pending)}</b></Typography.Text></Space>
      <Typography.Text type="secondary">最后心跳 {time(heartbeat)} · 当前 Release {releaseId ?? '未提供'}</Typography.Text>
    </Space>
  </Card>;
}
