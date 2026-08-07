# 研究环境（JupyterLab）

BulletTrade 提供 `bullet-trade lab`/`bullet-trade jupyterlab` 一键启动研究环境。默认根目录位于用户主目录下的 `bullet-trade`，集中存放 Notebook、`.env` 与输出。

首次运行要注意一下设置和目录：
![first-started](assets/jupyter-first-started.png)

## 默认路径与安全策略
- Notebook 根目录：macOS/Linux `~/bullet-trade`，Windows `~\\bullet-trade`
- 设置文件：`~/.bullet-trade/setting.json`，可调 `host`、`port`、`root_dir`、`env_path`、`open_browser`、`no_password`、`no_cert`、`token`
- `.env` 读取顺序：默认仅加载根目录下的 `.env`（不会读取当前工作目录的 `.env`）
- 默认监听 `127.0.0.1:8088`，开启 Jupyter token，未配置密码/证书；如需公网访问请务必配置密码或证书
- 研究文件读写：`read_file`/`write_file` 兼容聚宽，路径相对研究根目录；日志会打印相对/绝对路径，便于排查；若未初始化会提示运行 `bullet-trade lab`

运行后会自动打开浏览器：
![launcher](assets/jupyter-launcher.png)

## 首次运行会自动完成
1. 创建 `~/.bullet-trade/setting.json`、默认根目录与 `.env`。
2. 将安装目录的 `bullet_trade/notebook/` 样例复制到根目录（保留子目录结构，已存在同名文件跳过并在日志中提示）。
3. 写入 BulletTrade 代码片段设置，可在 Command Palette 搜索 “BulletTrade” 插入。
4. 打印当前使用的设置文件与 `.env` 路径，以及可修改的默认行为。

欢迎样例ipynb
![welcome](assets/jupyter-welcome.png)

## 因子研究（通用管线）
- 位置：`bullet_trade.research.factors` 提供因子管线（`run_factor_pipeline`）、评估与向量化回测（`evaluate_factor_performance`）、结果存储（`save_results`）。
- 典型流程：准备 DataFrame（`date/code/close/...` + 自定义因子函数）→ 过滤（停牌/涨跌停/ST/次新/到期日等）→ 因子去极值/标准化/中性化 → 多因子加权得分 → 分桶/IC/RankIC/长多/多空回测 → 结果落地 CSV/Parquet/SQLite。
- 成本模型：佣金/印花税/滑点 + 每笔固定费（可转债流量费等），在评估时统一扣减。
- 示例：`research/convertible_factor_example.py` 展示可转债溢价/双低因子从管线到评估的完整链路，结果默认写入研究目录下的 `results/`。

## 研究文件读写（兼容聚宽）
- 路径：`read_file(path)` / `write_file(path, content, append=False)` 的 `path` 需为研究根目录的相对路径，根目录来源于 `~/.bullet-trade/setting.json` 的 `root_dir`（无设置文件时默认 `~/bullet-trade`）。日志会打印相对路径与展开的绝对路径，方便确认读写位置。
- 初始化提示：若尚未创建研究根目录或设置文件，调用时会提示运行 `bullet-trade lab` 完成初始化，并标明预期路径。
- 写入：`content` 支持 `str`/`bytes`/`bytearray`/`memoryview`，字符串以 UTF-8 编码；`append=True` 追加写入，默认覆盖；父目录不存在时自动创建。
- 读写越界：绝对路径或试图跳出研究根目录会抛错，错误信息会包含相对与绝对路径。
- 示例：
  ```python
  import io, json
  from jqdata import read_file, write_file

  # 写入 CSV（覆盖）
  write_file("logs/out.csv", "a,b\n1,2\n", append=False)
  # 追加二进制
  write_file("logs/out.csv", b"3,4\n", append=True)
  # 读取原始字节并解析
  data = read_file("logs/out.csv")
  df = pd.read_csv(io.BytesIO(data))

  # 写入/读取 JSON
  write_file("data/hs300.json", json.dumps(get_index_stocks("000300.XSHG")))
  codes = json.loads(read_file("data/hs300.json"))
  ```


## 常用命令
- 启动研究环境（默认打开浏览器）：  
  ```bash
  bullet-trade lab
  ```
- 仅做依赖/端口诊断：  
  ```bash
  bullet-trade lab --diagnose
  ```
- 自定义监听或根目录：编辑 `~/.bullet-trade/setting.json`（如修改 `root_dir`、`env_path`、`host`、`port`），或临时使用 `--ip/--port/--notebook-dir` 覆盖。

系统部分api与聚宽对齐，下面是接入miniqmt配置后的数据获取样例：
![data](assets/jupyter-data.png)

## 与回测/实盘的衔接
- 在根目录 `.env` 配置数据源与券商参数，Notebook 中 `import bullet_trade` 或聚宽兼容 API 即可直接使用。
- 复用根目录运行命令行：  
  ```bash
  bullet-trade backtest strategies/demo_strategy.py --start 2025-01-01 --end 2025-06-01
  bullet-trade live strategies/demo_strategy.py --broker qmt
  ```

## 常见问题
- **端口占用**：使用 `bullet-trade lab --diagnose --port 8088` 查看占用，或在 `setting.json` 修改端口。  
- **无法写入目录**：确保根目录可写，必要时调整 `root_dir`。  
- **安全提示**：当监听非 127.0.0.1 且未配置密码/证书时，CLI 会拒绝启动；请配置密码/证书或改为 loopback。
