import { useEffect, useState } from 'react';
import { Alert, Button, Card, Collapse, DatePicker, Descriptions, Space, Table, Tag, Typography } from 'antd';
import { dataHubJobAction, getDataHubOverview, updateAllData, type DataHubOverview } from '../api';

const labels: Record<string, string> = { IDLE: '未开始', RUNNING: '进行中', UPDATED: '已更新', NO_CHANGE: '无变化', PARTIAL: '部分完成', FAILED: '失败', SOURCE_BLOCKED: '来源受阻', INTERRUPTED: '已中断', PASS: '通过', COMPLETED: '已结束' };
const reasons: Record<string, string> = { SYMBOL_DATA_ERROR: '估值解析异常', UNKNOWN_EMPTY: '空响应待确认', UNVERIFIED_COVERAGE: '无覆盖证明待核实', QUALITY_FAILURE: '数据校验未通过', FAILED: '采集失败', PENDING: '待处理', RUNNING: '处理中' };
const fmt = (v: number | undefined) => v == null ? '未统计' : v.toLocaleString();

export function DataStatus() {
  const [data, setData] = useState<DataHubOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [range, setRange] = useState<[string, string] | null>(null);
  const refresh = async () => {
    try { setData(await getDataHubOverview()); setError(null); }
    catch (e) { setError(String(e)); }
  };
  useEffect(() => { void refresh(); const id = window.setInterval(refresh, 4000); return () => window.clearInterval(id); }, []);
  const action = async (operation: () => Promise<unknown>) => {
    setBusy(true);
    try { const result = await operation() as { message?: string; status?: string }; setNotice(result.message ?? (result.status === 'ALREADY_RUNNING' ? '任务正在运行，请查看进度' : '操作已提交，请查看下方进度')); await refresh(); }
    catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  };
  const running = data?.update.status === 'RUNNING' || data?.job.worker_alive;
  const release = data?.release;
  const base = data?.base_coverage?.base_commit === release?.base_commit ? data?.base_coverage?.datasets : undefined;
  const statusPatch = release?.datasets.trade_status_daily;
  const rows = [
    { key: 'price', name: '行情', source: '基础库 · final 行情', published: base?.['行情'], downloaded: undefined, status: base?.['行情'] ? '可用 · 日频' : '待检查', dateLabel: '' },
    { key: 'status', name: 'ST / 停牌', source: statusPatch ? `基础库 · BaoStock 历史表；补充补丁 ${fmt(statusPatch.row_count)} 行（${statusPatch.first_date}）` : '基础库 · BaoStock 历史表', published: base?.['ST / 停牌'], downloaded: undefined, status: base?.['ST / 停牌'] ? '部分可用 · 注意日期' : '待检查', dateLabel: '' },
    { key: 'valuation_daily', name: '估值', source: '补充库 · 东方财富', published: release?.datasets.valuation_daily, downloaded: data?.job.counts.complete, status: release?.datasets.valuation_daily?.source?.some(s => s.includes('baostock')) ? '旧口径 · 新接口不可用' : release?.datasets.valuation_daily ? '部分可用' : '未发布', dateLabel: '' },
    { key: 'sw_industry_history', name: '行业', source: '补充库 · 申万', published: release?.datasets.sw_industry_history, downloaded: undefined, status: release?.datasets.sw_industry_history ? '部分可用 · 一级行业' : '未发布', dateLabel: '' },
    { key: 'security_lifecycle', name: '基础资料', source: '基础库 · Tushare 名录', published: release?.datasets.security_lifecycle, downloaded: undefined, status: release?.datasets.security_lifecycle ? '部分可用' : '未发布', dateLabel: '上市日期范围' },
  ];
  const stages = [['base', '同步基础库'], ['valuation', '更新估值'], ['industry', '更新行业'], ['lifecycle', '更新基础资料'], ['check', '自动检查'], ['publish', '发布结果']].map(([key, name]) => ({ key, name, ...data?.update.stages[key] }));
  const issues = data?.issues.length ? data.issues : data?.job.counts.failed ? [{ reason: 'FAILED', count: data.job.counts.failed, symbols: [] }] : [];
  return <Space direction="vertical" size={16} style={{ width: '100%' }}>
    <Space style={{ width: '100%', justifyContent: 'space-between' }}><Typography.Title level={4} style={{ margin: 0 }}>数据状态</Typography.Title><Button type="primary" loading={busy} disabled={!data || !!running} onClick={() => action(() => updateAllData())}>更新全部数据</Button></Space>
    {error && <Alert showIcon type="error" message="操作或状态读取失败" description={error} />}
    {notice && <Alert showIcon closable onClose={() => setNotice(null)} type="info" message={notice} />}
    <Card title="当前能用于回测的数据">
      <Table rowKey="key" pagination={false} size="middle" scroll={{ x: 900 }} dataSource={rows} columns={[
        { title: '数据', dataIndex: 'name' },
        { title: '实际读取来源', dataIndex: 'source' },
        { title: '已发布股票', render: (_, r) => fmt(r.published?.stocks) },
        { title: '已发布行数', render: (_, r) => fmt(r.published?.row_count ?? r.published?.rows) },
        { title: '日期范围', render: (_, r) => r.published?.first_date ? `${r.published.first_date} 至 ${r.published.latest_date ?? '未统计'}${r.dateLabel ? '（上市日期）' : ''}` : '未统计' },
        { title: '已下载股票', render: (_, r) => r.downloaded == null ? '—' : fmt(r.downloaded) },
        { title: '状态', dataIndex: 'status' },
      ]} />
      <Typography.Text type="secondary">发布于 {release?.published_at ? new Date(release.published_at).toLocaleString('zh-CN') : '未发布'}</Typography.Text>
      {data?.gap_plan && <Typography.Paragraph type="secondary" style={{ margin: '8px 0 0' }}>低 Beta 窗口 {data.gap_plan.strategy_window.start} 至 {data.gap_plan.strategy_window.end}：基础行情已满足；{data.gap_plan.strategy_gap.length ? `仍缺 ${data.gap_plan.strategy_gap.map(g => `${g.domain}（${g.range.start} 至 ${g.range.end}，${g.state}）`).join('；')}` : '没有已确认缺口'}。</Typography.Paragraph>}
      {data?.work_queue && <Typography.Paragraph type="secondary" style={{ margin: '0' }}>补数工作单：当前更新待处理 {data.work_queue.counts.current?.PENDING ?? 0}；策略缺口待处理 {data.work_queue.counts.strategy?.PENDING ?? 0}；历史修复待处理 {data.work_queue.counts.historical?.PENDING ?? 0}。</Typography.Paragraph>}
    </Card>
    <Card title={<Space>本次更新<Tag>{labels[data?.update.status ?? 'IDLE'] ?? data?.update.status}</Tag></Space>}>
      <Table rowKey="key" pagination={false} size="small" dataSource={stages} columns={[
        { title: '阶段', dataIndex: 'name' }, { title: '结果', render: (_, r) => labels[r.status ?? ''] ?? r.status ?? '待执行' },
        { title: '详情', render: (_, r) => r.reason ?? (r.accepted != null ? `通过 ${r.accepted}，隔离 ${r.isolated}` : '—') },
      ]} />
      {data?.update.error && <Alert type="error" message={data.update.error} />}
      <Space wrap style={{ marginTop: 12 }}><Typography.Text>估值下载：{fmt(data?.job.counts.complete)} 成功 / {fmt(data?.job.total_shards)} 总股票</Typography.Text><Typography.Text>{fmt(data?.job.rows_downloaded)} 行</Typography.Text><Typography.Text>失败 {fmt(data?.job.counts.failed)} · 未覆盖待核实 {fmt(data?.job.counts.not_covered)}</Typography.Text></Space>
      {data?.job.worker_alive && <Typography.Paragraph>当前股票：{data.job.current_shard ?? '等待响应'}</Typography.Paragraph>}
    </Card>
    <Card title="需要关注的问题">
      <Table rowKey="reason" pagination={false} size="small" dataSource={issues} columns={[
        { title: '问题', render: (_, r) => reasons[r.reason] ?? r.reason }, { title: '股票数', dataIndex: 'count' }, { title: '处理', render: () => '保留隔离；不计入新版本可用范围' },
      ]} locale={{ emptyText: data?.candidate ? '本次检查无隔离项' : '尚未生成候选检查报告' }} />
    </Card>
    <Collapse items={[{ key: 'advanced', label: '高级操作与版本详情', children: <Space direction="vertical" style={{ width: '100%' }}>
      <Space wrap><Button disabled={busy || !!running} onClick={() => action(() => updateAllData('audit'))}>检查候选数据</Button><Button disabled={busy || !!running || !data?.job.counts.failed} onClick={() => action(() => dataHubJobAction('repair'))}>重试失败项</Button><Button disabled={!data?.job.worker_alive || busy} onClick={() => action(() => dataHubJobAction('pause'))}>暂停采集</Button><DatePicker.RangePicker onChange={(_, values) => setRange(values[0] && values[1] ? values as [string, string] : null)} /><Button disabled={!range || busy || !!running} onClick={() => action(() => updateAllData('backfill', range?.[0], range?.[1]))}>历史回填</Button></Space>
      <Descriptions column={1} size="small"><Descriptions.Item label="版本">{release?.release_id ?? '—'}</Descriptions.Item><Descriptions.Item label="基础 commit">{release?.base_commit ?? '—'}</Descriptions.Item><Descriptions.Item label="补充 commit">{release?.supplemental_commit ?? '—'}</Descriptions.Item><Descriptions.Item label="候选版本">{data?.candidate?.candidate_id ?? '—'}</Descriptions.Item></Descriptions>
      <Typography.Text type="secondary">历史可得时点未完全验证；严格 PIT 策略不可按已验证数据使用。行业基础资料可能保留旧记录。</Typography.Text>
    </Space> }]} />
  </Space>;
}
