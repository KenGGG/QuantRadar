import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Collapse, Col, DatePicker, Descriptions, Row, Space, Table, Typography } from 'antd';
import { dataHubJobAction, getDataHubOverview, updateAllData, type DataHubOverview } from '../api';
import { DataActivitySummary } from './datahub/DataActivitySummary';
import { DataActivityCard } from './datahub/DataActivityCard';
import { DataCoverageTable } from './datahub/DataCoverageTable';

const reasons: Record<string, string> = { SYMBOL_DATA_ERROR: '估值解析异常', UNKNOWN_EMPTY: '空响应待确认', UNVERIFIED_COVERAGE: '无覆盖证明待核实', QUALITY_FAILURE: '数据校验未通过', FAILED: '采集失败', PENDING: '待处理', RUNNING: '处理中' };
const order: Record<string, number> = { current: 0, historical: 1, strategy: 2 };

export function DataStatus() {
  const [data, setData] = useState<DataHubOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [range, setRange] = useState<[string, string] | null>(null);
  const refresh = async () => { try { setData(await getDataHubOverview()); setError(null); } catch (e) { setError(String(e)); } };
  const activities = useMemo(() => [...(data?.activities ?? [])].sort((a, b) => (order[a.queue ?? ''] ?? 3) - (order[b.queue ?? ''] ?? 3)), [data?.activities]);
  const hasRunningActivity = activities.some(item => item.status === 'RUNNING');
  useEffect(() => { void refresh(); if (!hasRunningActivity) return; const id = window.setInterval(refresh, 4000); return () => window.clearInterval(id); }, [hasRunningActivity]);
  const action = async (operation: () => Promise<unknown>) => { setBusy(true); try { const result = await operation() as { message?: string; status?: string }; setNotice(result.message ?? (result.status === 'ALREADY_RUNNING' ? '任务正在运行，请查看进度' : '操作已提交')); await refresh(); } catch (e) { setError(String(e)); } finally { setBusy(false); } };
  const release = data?.release;
  const running = hasRunningActivity || data?.job.worker_alive;
  const base = data?.base_coverage?.base_commit === release?.base_commit ? data?.base_coverage?.datasets : undefined;
  const fallbackRows = [
    { key: 'price', name: '股票行情', published: base?.['行情'], usage: '可用', qualification: 'RAW_RESEARCH' },
    { key: 'status', name: 'ST/停牌', published: base?.['ST / 停牌'], usage: hasRunningActivity ? '补数中' : '部分覆盖', qualification: 'PARTIAL' },
    { key: 'valuation', name: 'PE/PB/PS', published: release?.datasets.valuation_daily, usage: '部分覆盖', qualification: 'RAW_RESEARCH' },
    { key: 'industry', name: '申万行业', published: release?.datasets.sw_industry_history, usage: '研究接口待开放', qualification: 'READABLE · PIT_PARTIAL' },
  ];
  const rows = data?.data_sources?.length ? data.data_sources.map(source => ({ key: `${source.domain}-${source.storage}`, name: source.name, published: source.coverage, usage: source.read_rule === '仅补基础库缺失记录' ? '补数中' : '可用', qualification: source.coverage?.qualification ?? '未提供' })) : fallbackRows;
  const issues = data?.issues?.length ? data.issues : [];
  const current = activities.find(item => item.queue === 'current');
  const historical = activities.find(item => item.queue === 'historical');
  const strategy = activities.find(item => item.queue === 'strategy');
  const strategyCompact = !!strategy && (strategy.task_progress.pending ?? 0) === 0 && (strategy.task_progress.running ?? 0) <= 1;
  return <Space direction="vertical" size={16} style={{ width: '100%' }}>
    <Space style={{ width: '100%', justifyContent: 'space-between' }}><Typography.Title level={4} style={{ margin: 0 }}>数据状态</Typography.Title><Button type="primary" loading={busy} disabled={!data || !!running} onClick={() => action(() => updateAllData())}>更新全部数据</Button></Space>
    {error && <Alert showIcon type="error" message="操作或状态读取失败" description={error} />}{notice && <Alert showIcon closable onClose={() => setNotice(null)} type="info" message={notice} />}
    <DataActivitySummary activities={activities} releaseId={release?.release_id} onRefresh={() => void refresh()} />
    <Card title="后台数据任务"><Row gutter={[16, 16]}>{current && <Col xs={24} xl={12}><DataActivityCard activity={current} /></Col>}{historical && <Col xs={24} xl={12}><DataActivityCard activity={historical} /></Col>}</Row>{strategy && (strategyCompact ? <Collapse style={{ marginTop: 16 }} items={[{ key: 'strategy', label: `策略专项补数 · ${strategy.task_progress.running ?? 0}项处理中`, children: <DataActivityCard activity={strategy} /> }]} /> : <Row style={{ marginTop: 16 }}><Col xs={24} xl={12}><DataActivityCard activity={strategy} /></Col></Row>)}{activities.length === 0 && <Typography.Text type="secondary">当前没有后台下载任务</Typography.Text>}</Card>
    <DataCoverageTable rows={rows} />
    <Card title="问题与高级操作"><Table rowKey="reason" pagination={false} size="small" dataSource={issues} columns={[{ title: '问题', render: (_, row) => reasons[row.reason] ?? row.reason }, { title: '股票数', dataIndex: 'count' }, { title: '处理', render: () => '保留隔离；不计入新版本可用范围' }]} locale={{ emptyText: '当前没有需要关注的问题' }} />
      <Collapse style={{ marginTop: 16 }} items={[{ key: 'advanced', label: '高级操作与版本详情', children: <Space direction="vertical" style={{ width: '100%' }}><Space wrap><Button disabled={busy || !!running} onClick={() => action(() => updateAllData('audit'))}>检查候选数据</Button><Button disabled={busy || !!running || !data?.job.counts.failed} onClick={() => action(() => dataHubJobAction('repair'))}>重试失败项</Button><DatePicker.RangePicker onChange={(_, values) => setRange(values[0] && values[1] ? values as [string, string] : null)} /><Button disabled={!range || busy || !!running} onClick={() => action(() => updateAllData('backfill', range?.[0], range?.[1]))}>历史回填</Button></Space><Descriptions column={1} size="small"><Descriptions.Item label="版本">{release?.release_id ?? '未提供'}</Descriptions.Item><Descriptions.Item label="基础 commit">{release?.base_commit ?? '未提供'}</Descriptions.Item><Descriptions.Item label="补充 commit">{release?.supplemental_commit ?? '未提供'}</Descriptions.Item></Descriptions><Typography.Text type="secondary">严格历史时点资格与技术细节在此展开查看。</Typography.Text></Space> }]} />
    </Card>
  </Space>;
}
