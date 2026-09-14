# Experiment 身份迁移验收

日期：2026-09-14。

对本地 PostgreSQL 的既有 `experiments` 表执行可重复迁移后，迁移前后记录数均为 2。数据库只保留 `uq_experiment_experiment_id` 唯一约束；`display_name` 没有唯一约束。

迁移按显示名称列的唯一约束语义删除历史约束，覆盖 PostgreSQL 列重命名后约束名称保持不变的情况。事务内在 DDL 后再次统计记录数，不一致即回滚。旧 JSON 实验仍由 `/api/experiments` 的 `legacy:` 只读标识返回。
