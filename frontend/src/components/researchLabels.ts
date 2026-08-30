const FIELD_LABELS: Record<string, string> = {
  metadata_count: "元数据数量", pdf_success: "PDF 成功", pdf_failed: "PDF 失败",
  parse_success: "解析成功", parse_failed: "解析失败", analysis_success: "分析成功", analysis_failed: "分析失败",
  digest_status: "日报状态", outbox_status: "发件箱状态", sent_at: "发送时间",
  latest_operation_status: "最近运行状态", runtime_seconds: "运行秒数",
  platform_order: "序号", title: "标题", institution: "机构", channel: "栏目",
  pdf_status: "PDF 状态", mineru_status: "MinerU 状态", agnes_status: "Agnes 状态",
  research_value: "研究价值", reproducibility: "可复现性", content_type: "内容类型",
  authors: "作者", publish_date: "发布日期", category: "分类", industry: "行业", security: "证券",
  source_report_id: "来源研报 ID", pdf_pages: "PDF 页数", platform_pages: "平台页数",
  page_count_match: "页数一致", pdf_sha256: "PDF SHA-256", parser: "解析器", parser_version: "解析器版本",
  parse_quality: "解析质量", markdown_sha256: "Markdown SHA-256", summary: "摘要", research_type: "研究类型", one_line_summary: "一句话摘要", key_points: "关键要点", core_conclusion: "核心结论", method_or_logic: "主要方法/逻辑", risks_or_limitations: "风险与局限",
  core_method: "核心方法", key_variables: "关键变量", main_conclusion: "主要结论",
  applicable_market: "适用市场", possible_quantradar_use: "QuantRadar 可用方向", risks_and_limitations: "风险与局限",
  status: "状态", model: "模型", agnes_version: "Agnes 版本", prompt_version: "提示词版本",
  schema_version: "Schema 版本", chunking_version: "分块版本", analysis_profile_hash: "分析配置哈希",
  analysis_hash: "分析哈希", attempt_count: "尝试次数", updated_at: "更新时间",
  stage: "阶段", attempt: "尝试次数", started_at: "开始时间", finished_at: "结束时间",
  success: "成功", failed: "失败", skipped: "跳过", completeness: "完整性", digest_hash: "日报哈希", created_at: "创建时间", last_error: "最近错误",
  char_count: "字符数", replacement_char_ratio: "替换字符占比", table_count: "表格数", image_count: "图片数",
};

const STAGE_LABELS: Record<string, string> = {
  COLLECT: "采集", "DOWNLOAD/PREPARE": "下载 / 准备", PREPARE: "准备", PARSE: "解析", ANALYZE: "分析", DIGEST: "生成日报", OUTBOX: "发件箱", FEISHU: "飞书",
};

const STATUS_LABELS: Record<string, string> = {
  SUCCESS: "成功", SENT: "已发送", COMPLETE: "完整", READY: "已就绪", PENDING: "等待处理", RUNNING: "运行中", MISSING: "暂无记录", UNSUPPORTED: "不支持", FAILED: "失败", FAILED_RETRYABLE: "失败（可重试）", FAILED_PERMANENT: "失败（不可重试）", SKIPPED: "已跳过", PARSE_OK: "解析成功",
};

export function researchFieldLabel(field: string): string { return FIELD_LABELS[field] || field; }
export function researchStageLabel(stage: string): string { return STAGE_LABELS[stage] || stage; }
export function researchStatusLabel(status?: string | null): string { return STATUS_LABELS[status || "MISSING"] || status || STATUS_LABELS.MISSING; }
export function researchValueLabel(field: string | undefined, value: string): string {
  if (field === "research_type") return ({ MARKET: "市场研究", QUANT: "量化研究" } as Record<string, string>)[value] || value;
  if (field === "research_value" || field === "reproducibility") return ({ HIGH: "高", MEDIUM: "中", LOW: "低" } as Record<string, string>)[value] || value;
  if (field === "content_type") return ({ web: "网页", pdf: "PDF" } as Record<string, string>)[value] || value;
  if (field === "status") return researchStatusLabel(value);
  return value;
}
