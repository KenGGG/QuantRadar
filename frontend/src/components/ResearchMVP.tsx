import { useEffect, useState } from "react";
import { Alert, Card, Empty, Select, Space, Spin, Table, Tag, Typography } from "antd";
import {
  listResearchDates,
  listResearchReports,
  getResearchStatus,
  type ResearchChannel,
  type ResearchReport,
} from "../api";

const CHANNELS: Array<{ key: ResearchChannel; label: string }> = [
  { key: "HOT", label: "热门研报" },
  { key: "STRATEGY", label: "策略研究" },
  { key: "FINANCIAL_ENGINEERING", label: "金融工程" },
];

function statusTag(status: string) {
  const color = status === "SUCCESS" ? "green" : status === "UNSUPPORTED" ? "default" : status === "FAILED" ? "red" : "blue";
  return <Tag color={color}>{status}</Tag>;
}

export function ResearchMVP() {
  const [dates, setDates] = useState<string[]>([]);
  const [targetDate, setTargetDate] = useState<string>();
  const [channel, setChannel] = useState<ResearchChannel>("HOT");
  const [reports, setReports] = useState<ResearchReport[]>([]);
  const [counts, setCounts] = useState<Partial<Record<ResearchChannel, number>>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  useEffect(() => {
    listResearchDates()
      .then(({ dates: collectedDates }) => {
        setDates(collectedDates);
        setTargetDate(collectedDates[0]);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法读取采集记录"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!targetDate) {
      setReports([]);
      return;
    }
    setLoading(true);
    listResearchReports(targetDate, channel)
      .then(({ reports: rows }) => setReports(rows))
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "无法读取研报列表"))
      .finally(() => setLoading(false));
    getResearchStatus(targetDate)
      .then(({ channels }) => setCounts(channels))
      .catch(() => setCounts({}));
  }, [targetDate, channel]);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>研报</Typography.Title>
        <Typography.Text type="secondary">企业预警采集结果；展示顺序与栏目保持平台原始顺序。</Typography.Text>
      </div>
      {error && <Alert type="warning" showIcon message="研报存储暂不可用" description={error} />}
      <Card>
        <Space wrap>
          <Typography.Text>采集日期</Typography.Text>
          <Select
            style={{ minWidth: 150 }}
            value={targetDate}
            placeholder="暂无已采集日期"
            options={dates.map((value) => ({ value, label: value }))}
            onChange={setTargetDate}
          />
          <Select
            style={{ minWidth: 130 }}
            value={channel}
            options={CHANNELS.map(({ key, label }) => ({ value: key, label }))}
            onChange={(value) => setChannel(value as ResearchChannel)}
          />
        </Space>
        {targetDate && <Space style={{ marginLeft: 20 }} wrap>
          {CHANNELS.map(({ key, label }) => <Tag key={key}>{label} {counts[key] ?? 0} 篇</Tag>)}
        </Space>}
      </Card>
      <Card title={CHANNELS.find((item) => item.key === channel)?.label}>
        {loading ? <div style={{ textAlign: "center", padding: 36 }}><Spin /></div> : !targetDate ? <Empty description="尚无已采集研报；完成采集后将在此显示。" /> : (
          <Table<ResearchReport>
            rowKey="id"
            pagination={{ pageSize: 20, showSizeChanger: false }}
            dataSource={reports}
            columns={[
              { title: "序号", dataIndex: "platform_order", width: 80 },
              { title: "标题", dataIndex: "title" },
              { title: "机构", dataIndex: "institution", width: 180, render: (value) => value || "—" },
              { title: "类型", dataIndex: "content_type", width: 100 },
              { title: "处理状态", dataIndex: "status", width: 120, render: statusTag },
            ]}
          />
        )}
      </Card>
    </Space>
  );
}
