import { Card, Descriptions, Progress, Space, Tag, Tooltip, Typography } from 'antd';
import type { DataHubActivity } from '../../api';

const fmt = (value: number | null | undefined) => value == null ? '未提供' : value.toLocaleString();
const queueMeta: Record<string, { title: string; note: string; range: string }> = {
  current: { title: '近期状态维护', note: '正在补最近20个交易日缺失的 ST / 停牌状态。', range: '最近20交易日' },
  historical: { title: '历史状态修复', note: '正在逐步修复历史上市存续期内的状态缺口。', range: '历史范围' },
  strategy: { title: '策略专项补数', note: '用于旧策略专项缺口检查，优先级低于日常和历史维护。', range: '专项范围' },
};
const statusMeta: Record<string, { label: string; color?: string }> = { RUNNING: { label: '进行中', color: 'processing' }, PENDING: { label: '待处理' }, COMPLETED: { label: '已完成', color: 'success' }, SOURCE_BLOCKED: { label: '来源受限', color: 'warning' }, FAILED: { label: '失败', color: 'error' } };
const time = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '未提供';

export function DataActivityCard({ activity }: { activity: DataHubActivity }) {
  const meta = queueMeta[activity.queue ?? ''] ?? { title: activity.label, note: '后台数据任务。', range: '未提供' };
  const status = statusMeta[activity.status] ?? { label: activity.status };
  const coverage = activity.coverage_progress;
  const parts = activity.adapter?.split('.') ?? [];
  const adapter = parts[parts.length - 1] ?? activity.endpoint ?? '未提供';
  return <Card size="small" title={<Space><Typography.Text strong>{meta.title}</Typography.Text><Tag color={status.color}>{status.label}</Tag></Space>}>
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Typography.Text>{activity.label}</Typography.Text><Typography.Text type="secondary">{meta.note}</Typography.Text>
      <Space wrap><Tag>{activity.source ?? '未提供'}</Tag><Tooltip title={activity.adapter ?? activity.endpoint ?? undefined}><Typography.Text type="secondary">{adapter}</Typography.Text></Tooltip></Space>
      <Typography.Text type="secondary">{activity.queue ?? '未提供'} · {meta.range}</Typography.Text>
      {coverage ? <><Typography.Text strong>数据完整度 {coverage.percentage == null ? '未提供' : `${coverage.percentage.toFixed(2)}%`}</Typography.Text><Progress percent={coverage.percentage ?? 0} showInfo={false} />
        <Typography.Text type="secondary">{fmt(coverage.valid_fields)} / {fmt(coverage.expected_fields)} 个字段</Typography.Text>
        <Descriptions size="small" column={2}><Descriptions.Item label="完整股票">{fmt(coverage.complete)} / {fmt(coverage.eligible)}</Descriptions.Item><Descriptions.Item label="部分缺失">{fmt(coverage.partial)}</Descriptions.Item><Descriptions.Item label="来源受限">{fmt(activity.task_progress.source_limited)}</Descriptions.Item></Descriptions>
      </> : <Typography.Text type="secondary">全历史完整度：尚未完成最新汇总</Typography.Text>}
      <Typography.Text>后台处理进度 {activity.task_progress.percentage == null ? '未提供' : `${activity.task_progress.percentage.toFixed(1)}%`}</Typography.Text><Progress size="small" percent={activity.task_progress.percentage ?? 0} status={activity.status === 'RUNNING' ? 'active' : 'normal'} showInfo={false} />
      <Typography.Text type="secondary">表示任务处理进度，不代表数据完整度</Typography.Text>
      <Descriptions size="small" column={2}><Descriptions.Item label="已处理">{fmt(activity.task_progress.completed)}</Descriptions.Item><Descriptions.Item label="待处理">{fmt(activity.task_progress.pending)}</Descriptions.Item><Descriptions.Item label="正在处理">{fmt(activity.task_progress.running)}</Descriptions.Item><Descriptions.Item label="范围">{activity.range.start && activity.range.end ? `${activity.range.start} → ${activity.range.end}` : '未提供'}</Descriptions.Item><Descriptions.Item label="最后心跳">{time(activity.last_heartbeat)}</Descriptions.Item>{activity.current_item && <Descriptions.Item label="当前">{activity.current_item === '当前批次处理中' ? '批量处理中' : activity.current_item}</Descriptions.Item>}</Descriptions>
    </Space>
  </Card>;
}
