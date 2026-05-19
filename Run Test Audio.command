#!/bin/zsh
cd "$(dirname "$0")"

if [ ! -x "venv/bin/python" ]; then
  echo "没有找到 venv/。请先双击 Setup MLX Test Env.command。"
  read "?按回车关闭..."
  exit 1
fi

venv/bin/python scripts/run_test_audio.py --seconds 60
echo ""
read "?按回车关闭..."
