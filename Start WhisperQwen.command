#!/bin/zsh
cd "$(dirname "$0")"

if [ ! -x "venv/bin/python" ]; then
  echo "没有找到 venv/。请先双击 Setup MLX Test Env.command。"
  read "?按回车关闭..."
  exit 1
fi

# 检查 ollama 是否在跑（不主动启动，避免抢用户的进程管理）
if ! curl -s --max-time 1 http://127.0.0.1:11434/api/tags > /dev/null; then
  echo "Ollama 没在跑。请先在另一个终端运行："
  echo "  ollama serve"
  echo "或者："
  echo "  brew services start ollama"
  echo ""
  read "?按回车关闭..."
  exit 1
fi

venv/bin/python launch_app.py
