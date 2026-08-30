import assert from "node:assert/strict";
import test from "node:test";

import { researchFieldLabel, researchStageLabel, researchStatusLabel, researchValueLabel } from "../src/components/researchLabels.ts";

test("Research 页面将通用字段、阶段和状态显示为中文", () => {
  assert.equal(researchFieldLabel("metadata_count"), "元数据数量");
  assert.equal(researchFieldLabel("research_value"), "研究价值");
  assert.equal(researchStageLabel("DOWNLOAD/PREPARE"), "下载 / 准备");
  assert.equal(researchStatusLabel("FAILED_RETRYABLE"), "失败（可重试）");
  assert.equal(researchStatusLabel("SENT"), "已发送");
  assert.equal(researchFieldLabel("agnes_version"), "Agnes 版本");
  assert.equal(researchValueLabel("research_type", "MARKET"), "市场研究");
  assert.equal(researchValueLabel("reproducibility", "HIGH"), "高");
});
