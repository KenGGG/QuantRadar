# 旧功能代码专项清理

2026-10-09，按用户最新要求，取代此前“保留V1源码”的决定。没有重写已验收V2引擎适配和运行存储。

删除588个已核验的旧源码/配置文件，及旧前端测试/占位文件。已移除 backend/quantradar、旧frontend入口/组件/构建、旧tests/examples/scripts、kronos_runtime、models、strategies、deploy、vendor、旧CI/Makefile/Linux启动/.env示例和旧依赖清单。V2不导入上述代码；真实BulletTrade加载自D:/Projects/BulletTrade，外部引擎未修改。

仅保留 backend/quantradar2、frontend/src/v2、scripts/v2_*、tests/v2、examples/v2、本次docs、var、当前环境与Node依赖。唯一依赖声明pyproject.toml，唯一完整环境快照requirements.lock；不再保留requirements-v2.txt/dev.txt/v2.lock及旧requirements.txt。完整环境锁包含BulletTrade报告功能的传递依赖，不把它当作应用直接依赖清单。前端未使用的ECharts两个直接依赖及对应传递包已卸载，标准dev/build统一V2配置。

初始批量删除被自动审批拒绝，要求证明依赖及保护运行数据；随后静态分析V2后端/脚本/测试无旧包导入、核验实际引擎路径、先整合依赖，再执行明确旧源码删除。

旧Kronos reports中18文件备份至系统临时目录：C:/Users/ken/AppData/Local/Temp/quantradar-v1-reports-e82fbaf1b8374d2881399802828ad14a.zip，核验ZIP条目后移除项目目录。root logs/app.log实际由当前V2原生依赖使用，未删除日志内容：停止本应用后迁入var/quantradar2/logs，API及验收/测试日志配置修正，避免重新生成根logs。未停止QMT/数据服务。

验证：18项V2测试通过；标准npm build含TypeScript检查通过；pip check无破损依赖。原有TestClient弃用、大包体警告保留。服务重启后status=ok、trading=false、worker_error=null，保留主SQLite与历史任务。浏览器与最后目录复核见当前清理结果记录。没有修改四份冻结包或引擎适配身份；本轮是删旧代码和配置，不是另启G3。
