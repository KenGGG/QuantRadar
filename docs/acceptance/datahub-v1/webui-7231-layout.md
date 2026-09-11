# 7231 数据状态布局验收（2026-09-10）

用户实际端口原先运行 main 旧代码，Job API 返回 SPA HTML。现在用户级 transient systemd unit `quantradar-webui.service` 托管 7231，通过 --app-dir 加载 datahub-v1 worktree；主目录 .env 的 QUANTRADAR_APP_ROOT 与 launcher 同步。此 unit 脱离终端运行，尚未配置开机持久安装。

页面分为采集任务、来源请求状态、正式研究数据与覆盖、折叠版本诊断/行情查询。4 秒轮询保留；请求错误显式展示；行情按需查询；正式版本与 staging 进度分开。Job 状态只读查询不再保存 lifecycle raw；未创建 Journal 的待处理股票计入 pending；DONE 不再在有 pending 时显示 COMPLETED。

真实浏览器访问 127.0.0.1:7231，刷新后重新进入数据状态：1280 px 无横向溢出，显示 1070/4916、946 COMPLETE、124 NOT_COVERED、3846 PENDING、1956718 行。Governor COOLDOWN；原采集 PID 已退出，页面显式提示 worker 未运行。ETA 在 worker 未运行时不展示。

验证：frontend npm build 成功；PYTHONPATH=backend pytest tests/unit/test_datahub.py 41 passed。首次未指定 PYTHONPATH 时测试加载 main 包失败，修正后通过。截图 webui-7231-layout.png。

本次仅验收布局、真实端口部署和读取展示；Start/Pause/Resume/Stop 全生命周期、自动恢复与发布闭环尚未完成真实浏览器验收，Goal 保持 IN_PROGRESS。当前正式版本仍是历史有限验证版本，其 schema 审计异常保留展示，不代表此次 Eastmoney 全市场结果已发布。
