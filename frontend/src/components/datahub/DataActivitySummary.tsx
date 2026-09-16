import { Button, Card, Space, Tag, Typography } from 'antd';
import type { DataHubActivity } from '../../api';

const fmt = (value: number | null | undefined) => value == null ? '未提供' : value.toLocaleString();
const time = (value: string | null | undefined) => value ? new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '未提供';

export function DataActivitySummary({ activities, releaseId, onRefresh }: { activities: DataHubActivity[]; releaseId?: string; onRefresh: () => void }) {
  const running = activities.filter(item => item.status === 'RUNNING');
  const sourceCount = new Set(running.map(item => item.source_contract_id).filter(Boolean)).size;
  const processing = activities.reduce((sum, item) => sum + (item.task_progress.running ?? 0), 0);
  const pending = activities.reduce((sum, item) => sum + (item.task_progress.pending ?? 0), 0);
  const heartbeats = activities.map(item => item.last_heartbeat).filter((item): item is string => Boolean(item)).sort();
  const heartbeat = heartbeats[heartbeats.length - 1];
  return <Card title="后台运行概览" extra={<Button onClick={onRefresh}>立即刷新</Button>}>
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Space><Tag color={running.length ? 'processing' : 'default'}>{running.length ? '数据维护进行中' : '当前无运行任务'}</Tag>{running.length ? <Typography.Text type="secondary">自动刷新中 · 4秒</Typography.Text> : <Typography.Text type="secondary">自动刷新已停止</Typography.Text>}</Space>
      <Space wrap size="large"><Typography.Text>活跃数据源 <b>{fmt(sourceCount)}</b></Typography.Text><Typography.Text>活跃任务流 <b>{fmt(running.length)}</b></Typography.Text><Typography.Text>正在处理 <b>{fmt(processing)}</b></Typography.Text><Typography.Text>待处理 <b>{fmt(pending)}</b></Typography.Text></Space>
      <Typography.Text type="secondary">最后心跳 {time(heartbeat)} · 当前 Release {releaseId ?? '未提供'}</Typography.Text>
    </Space>
  </Card>;
}
