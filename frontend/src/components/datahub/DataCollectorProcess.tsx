import { Card, Collapse, Descriptions, Progress, Space, Table, Tag, Tooltip, Typography } from 'antd';
import type { DataHubActivity } from '../../api';

const queueMeta: Record<string, { title: string; purpose: string }> = {
  current: { title: '近期状态维护', purpose: '近期状态维护' },
  historical: { title: '历史状态修复', purpose: '历史状态修复' },
  strategy: { title: '策略专项补数', purpose: '策略专项检查' },
};
const fmt = (value: number | null | undefined) => value == null ? '未提供' : value.toLocaleString();
const time = (value: string | null | undefined) => value ? new Date(value).toLocaleString('zh-CN') : '未提供';

export type CollectorProcess = {
  key: string; source: string | null; adapter: string | null; endpoint: string | null; dataset: string;
  activities: DataHubActivity[]; status: string; pending: number; heartbeat: string | null;
};

export function groupCollectorProcesses(activities: DataHubActivity[]): CollectorProcess[] {
  const groups = new Map<string, DataHubActivity[]>();
  activities.forEach(activity => {
    const key = [activity.source ?? '', activity.adapter ?? activity.endpoint ?? '', activity.dataset].join('|');
    groups.set(key, [...(groups.get(key) ?? []), activity]);
  });
  return [...groups.entries()].map(([key, members]) => ({
    key, source: members[0].source, adapter: members[0].adapter, endpoint: members[0].endpoint, dataset: members[0].dataset,
    activities: members, status: members.some(item => item.status === 'PUBLISHING') ? 'PUBLISHING' : members.some(item => item.status === 'WAITING_PUBLISH') ? 'WAITING_PUBLISH' : members.some(item => item.status === 'RUNNING') ? 'RUNNING' : members.some(item => item.status === 'PENDING') ? 'PENDING' : 'COMPLETED',
    pending: members.reduce((sum, item) => sum + (item.task_progress.pending ?? 0), 0),
    heartbeat: members.map(item => item.last_heartbeat).filter((item): item is string => Boolean(item)).sort().pop() ?? null,
  }));
}

export function DataCollectorProcessCard({ collector }: { collector: CollectorProcess }) {
  const running = collector.activities.filter(item => (item.task_progress.running ?? 0) > 0);
  const active = running.length ? running : collector.activities.filter(item => item.status === 'RUNNING');
  const work = active.map(item => queueMeta[item.queue ?? '']?.purpose ?? item.queue ?? '未提供').filter((item, index, values) => values.indexOf(item) === index);
  const currentItems = active.flatMap(item => item.current_items ?? []).filter((item, index, values) => values.indexOf(item) === index);
  const currentCoverage = collector.activities.find(item => item.queue === 'current')?.coverage_progress;
  const adapterParts = collector.adapter?.split('.') ?? [];
  const shortAdapter = adapterParts[adapterParts.length - 1] ?? collector.endpoint ?? '未提供';
  const title = `${collector.source ?? '未提供'} ${collector.dataset === 'trade_status' ? 'ST / 停牌采集' : collector.dataset === 'valuation_daily' ? '估值采集' : `${collector.dataset} 采集`}`;
  const statusText = collector.status === 'RUNNING' ? '采集中' : collector.status === 'WAITING_PUBLISH' ? '等待发布' : collector.status === 'PUBLISHING' ? '发布中' : collector.status === 'PENDING' ? '待处理' : '已完成';
  const details = collector.activities.map(activity => ({ key: activity.activity_id, queue: activity.queue ?? '未提供', purpose: queueMeta[activity.queue ?? '']?.title ?? activity.queue ?? '未提供', running: activity.task_progress.running, pending: activity.task_progress.pending, completed: activity.task_progress.completed }));
  return <Card title={<Space><Typography.Text strong>{title}</Typography.Text><Tag color={collector.status === 'RUNNING' || collector.status === 'PUBLISHING' ? 'processing' : undefined}>{statusText}</Tag></Space>}>
    <Space direction="vertical" size={10} style={{ width: '100%' }}>
      <Space wrap><Tag>{collector.source ?? '未提供'}</Tag><Tooltip title={collector.adapter ?? collector.endpoint ?? undefined}><Typography.Text type="secondary">{shortAdapter}</Typography.Text></Tooltip></Space>
      <Typography.Text>{collector.status === 'WAITING_PUBLISH' ? '已暂存：等待 Dolt 串行发布' : `正在下载：${collector.dataset === 'trade_status' ? 'ST / 停牌' : collector.dataset === 'valuation_daily' ? 'PE / PB / PS / PCF' : collector.dataset}`}</Typography.Text>
      <Descriptions size="small" column={{ xs: 1, sm: 2 }}><Descriptions.Item label="当前工作">{work.length ? work.join(' + ') : '批量处理中'}</Descriptions.Item><Descriptions.Item label="当前证券">{currentItems[0] ?? '批量处理中'}</Descriptions.Item><Descriptions.Item label="当前批次">{fmt(running.reduce((sum, item) => sum + (item.task_progress.running ?? 0), 0))}项</Descriptions.Item><Descriptions.Item label="后台待处理">{fmt(collector.pending)}</Descriptions.Item><Descriptions.Item label="最后心跳">{time(collector.heartbeat)}</Descriptions.Item></Descriptions>
      {currentCoverage && <><Typography.Text strong>数据完整度 {currentCoverage.percentage == null ? '未提供' : `${currentCoverage.percentage.toFixed(2)}%`}</Typography.Text><Progress percent={currentCoverage.percentage ?? 0} showInfo={false} /><Typography.Text type="secondary">{fmt(currentCoverage.valid_fields)} / {fmt(currentCoverage.expected_fields)} 个字段；这是数据完整度，不是下载进度。</Typography.Text></>}
      <Collapse items={[{ key: 'queues', label: '查看任务详情', children: <Table rowKey="key" pagination={false} size="small" dataSource={details} columns={[{ title: '队列', dataIndex: 'queue' }, { title: '用途', dataIndex: 'purpose' }, { title: '正在处理', render: (_, row) => fmt(row.running) }, { title: '待处理', render: (_, row) => fmt(row.pending) }, { title: '已完成', render: (_, row) => fmt(row.completed) }]} /> }]} />
    </Space>
  </Card>;
}
