#!/bin/zsh
cd "$(dirname "$0")"

LOG_DIR="$HOME/Library/Logs/Liasse"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/launch.log"

# 日志轮转：保留上一次的 launch.log 作为 .prev，方便对比
[ -f "$LOG" ] && mv "$LOG" "$LOG.prev"

{
  echo "==== launch $(date '+%Y-%m-%d %H:%M:%S') ===="
  echo "cwd=$(pwd)"
  echo "PATH=$PATH"
} >> "$LOG"

if [ ! -x "venv/bin/python" ]; then
  echo "没有找到 venv/。请先双击 Setup MLX Test Env.command。" | tee -a "$LOG"
  read "?按回车关闭..."
  exit 1
fi

# 检查 ollama 是否在跑（不主动启动，避免抢用户的进程管理）
if ! curl -s --max-time 1 http://127.0.0.1:11434/api/tags > /dev/null; then
  {
    echo "Ollama 没在跑。请先在另一个终端运行："
    echo "  ollama serve"
    echo "或者："
    echo "  brew services start ollama"
    echo ""
  } | tee -a "$LOG"
  read "?按回车关闭..."
  exit 1
fi

echo "日志写入：$LOG"
echo "如果闪退，复制下面命令到终端看最后 200 行："
echo "  tail -200 \"$LOG\""
echo ""

# 同时输出到 Terminal 和 log（PYTHONUNBUFFERED 保证 print/异常即时落盘）
PYTHONUNBUFFERED=1 LIASSE_VERBOSE=1 venv/bin/python launch_app.py 2>&1 | tee -a "$LOG"
EXIT_CODE=${pipestatus[1]}
echo "==== exit code=$EXIT_CODE at $(date '+%Y-%m-%d %H:%M:%S') ====" >> "$LOG"
if [ "$EXIT_CODE" != "0" ]; then
  echo ""
  echo "Liasse 异常退出（exit=$EXIT_CODE）。日志在：$LOG"
  read "?按回车关闭..."
fi
exit $EXIT_CODE
