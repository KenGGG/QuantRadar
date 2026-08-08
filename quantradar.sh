#!/usr/bin/env bash
# QuantRadar 启动 / 重启 / 关闭 管理脚本
#
# 应用仅由一个 uvicorn 进程组成（FastAPI 同时托管前端 frontend/dist，
# 异步回测 Worker 以 daemon 线程运行在该进程内）。
# Dolt(investment_data, 3307) 与 PostgreSQL(落库) 为外部依赖，本脚本只做可达性预检，
# 不负责它们的启停。
#
# 用法:
#   ./quantradar.sh start      # 启动（后台，写 PID + 日志）
#   ./quantradar.sh stop       # 优雅停止；超时则强杀
#   ./quantradar.sh restart    # stop + start
#   ./quantradar.sh status     # 查看运行状态与访问地址
#
# 环境变量（可选覆盖）:
#   QUANTRADAR_HOST  默认 127.0.0.1
#   QUANTRADAR_PORT  默认 8000

set -euo pipefail

# ---- 路径解析（脚本所在目录即项目根） ----
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

APP_NAME="QuantRadar"
VENV="$ROOT_DIR/.venv"
PYTHON="$VENV/bin/python"
UVICORN="$VENV/bin/uvicorn"
APP_MODULE="quantradar.api.app:app"

HOST="${QUANTRADAR_HOST:-127.0.0.1}"
PORT="${QUANTRADAR_PORT:-8000}"

LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/quantradar.pid"
LOG_FILE="$LOG_DIR/quantradar.log"

# ---- 依赖检查 ----
if [[ ! -x "$PYTHON" ]]; then
  echo "[$APP_NAME] 错误：未找到虚拟环境 $VENV" >&2
  echo "            请先执行 'make setup' 安装依赖。" >&2
  exit 1
fi

# ---- 运行状态判断 ----
is_running() {
  [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

# ---- 外部依赖预检（仅警告，不阻断启动） ----
preflight() {
  if (exec 3<>/dev/tcp/127.0.0.1/3307) 2>/dev/null; then
    echo "[$APP_NAME] 预检：investment_data (Dolt 3307) 可达 ✅"
    exec 3>&- 3<&-
  else
    echo "[$APP_NAME] 警告：investment_data (Dolt 3307) 不可达 —— 回测将无法读取真实行情。" >&2
    echo "            请先在本机启动 investment_data 的 Dolt SQL server。" >&2
  fi
}

# ---- 启动 ----
do_start() {
  if is_running; then
    echo "[$APP_NAME] 已在运行 (PID=$(cat "$PID_FILE")) -> http://$HOST:$PORT"
    return 0
  fi
  mkdir -p "$LOG_DIR"
  preflight
  echo "[$APP_NAME] 正在启动 uvicorn ($APP_MODULE) ..."
  # nohup 在输出已重定向时直接 exec 目标进程，故 $! 即 uvicorn 的 PID；日志全量写入 LOG_FILE
  nohup "$UVICORN" "$APP_MODULE" \
    --host "$HOST" --port "$PORT" \
    > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  # 稍候确认进程存活
  sleep 2
  if is_running; then
    echo "[$APP_NAME] 已启动 (PID=$(cat "$PID_FILE")) -> http://$HOST:$PORT"
    echo "            日志: $LOG_FILE"
  else
    echo "[$APP_NAME] 启动失败，请查看日志: $LOG_FILE" >&2
    rm -f "$PID_FILE"
    exit 1
  fi
}

# ---- 停止 ----
do_stop() {
  if ! is_running; then
    echo "[$APP_NAME] 未在运行（无有效 PID 或无进程）"
    rm -f "$PID_FILE"
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  echo "[$APP_NAME] 正在停止 (PID=$pid) ..."
  kill "$pid" 2>/dev/null || true
  # 等待优雅退出，最多 ~10s
  local waited=0
  while kill -0 "$pid" 2>/dev/null; do
    sleep 1
    waited=$((waited + 1))
    if (( waited >= 10 )); then
      echo "[$APP_NAME] 超时未退出，强制终止 (SIGKILL) ..."
      kill -9 "$pid" 2>/dev/null || true
      break
    fi
  done
  rm -f "$PID_FILE"
  echo "[$APP_NAME] 已停止"
}

# ---- 状态 ----
do_status() {
  if is_running; then
    echo "[$APP_NAME] 运行中 (PID=$(cat "$PID_FILE")) -> http://$HOST:$PORT"
  else
    echo "[$APP_NAME] 未运行"
    rm -f "$PID_FILE" 2>/dev/null || true
  fi
}

usage() {
  echo "用法: $0 {start|stop|restart|status}"
}

case "${1:-}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; do_start ;;
  status)  do_status ;;
  *)       usage; exit 1 ;;
esac
