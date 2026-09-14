# ETF 研究与 FactorLab 浏览器验收

日期：2026-09-14；本机 FastAPI：`127.0.0.1:7231`；固定 release：`R9c1b6c13965dc457`。

- 页面菜单可打开 ETF 研究与 FactorLab。
- FactorLab 页面显示固定 release 的 base／supplemental commit、日期区间、Alpha 编号输入、1／5／20 日标签、60%／20%／20% 分段、静态池选择及 101 项目录中的 82 个 READY 量价项。
- ETF 页面显示固定版本、初始资金、单边滑点 bp、五模板、行业身份表和预检按钮。
- FactorLab 可输入已有的不可变批次 ID 并恢复该批次的摘要；实测加载
  `66d65c9d-5f24-4b4a-a5f4-54889cc2ae19` 后显示 `SUCCESS: 5/5`、逐因子的
  `CACHE_HIT` 状态以及受注册表约束的 1 日／5 日评价统计链接。
- 同一批次的“计算相关性”页面展示研究／验证段完全链接规则、带符号的相关系数、
  有效日期和“样本不足”配对；未点击冻结代表因子或访问保留段。
- 自动化回归覆盖代表因子理由必填、冻结后拒绝改写，以及未冻结时保留段接口拒绝访问。
- FactorLab 批次摘要将研究流程状态单独返回为 `NOT_READY`、
  `AWAITING_RESEARCHER_SELECTION`、`FROZEN_AWAITING_HOLDOUT_EVALUATION` 或
  `HOLDOUT_ACCESSED`；生产构建根据该字段将等待研究判断显示为警示而非技术 BLOCKED。
- 对 2021-01-04 至 2021-03-31 的全模板网页预检显示：等权 2 个缺失依赖，动量、趋势、逆波动率与 ERC 各 1 个；五个行业 ETF 均 BLOCKED，且均明确说明没有可验证跟踪指数身份。
- 浏览器控制台除浏览器请求 `/favicon.ico` 的历史 404 外无应用错误；加载当前构建产物后的 ETF／FactorLab 验收期间控制台为 0 errors。
