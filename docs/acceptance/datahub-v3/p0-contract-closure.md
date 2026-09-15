# DataHub V3 P0 契约收尾

本记录落实《QuantRadar 代码与数据基础审查》中不扩 schema 或数据域的三项收尾。

- `financial_statement()` 现在必须声明 `mapping_version`，因此同一原始报表的多个解释版本不会被静默混合。`as_of` 约束保守可得时间；`observed_before` 约束本地已观察时间；`strict_pit=True` 必须提供该观察边界，且只接受 `pit_status=PASS`。
- 指数快照的修订链以 `dataset_type + index_code + source_date + source` 隔离。新库的唯一索引包含 `source`；已有补充库会在下一次 `ensure_schema()` 时就地升级该索引。
- 财务原始版本与映射写入不再使用 `INSERT IGNORE`。同一不可变键若字段不同会拒绝并报错，相同内容才视为幂等。
- `ACTIVE_PHASE.md` 与 `CURRENT_STATE.md` 将遗留 Alpha101/ETF 和 DataHub V1 表述明确标记为历史，当前里程碑保持 `CLOSED`。

验证：`PYTHONPATH=backend .venv/bin/python -m pytest tests/unit/test_datahub.py tests/unit/test_datahub_inventory.py tests/unit/test_datahub_remediation.py tests/unit/test_datahub_v3_contracts.py tests/unit/test_financial_canonical.py -q`，结果为 **152 passed**。这是代码契约验证；它不声称已经对本机补充库执行迁移或扩大任何数据覆盖范围。
