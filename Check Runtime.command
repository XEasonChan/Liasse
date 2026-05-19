#!/bin/zsh
cd "$(dirname "$0")"

if [ -x "venv/bin/python" ]; then
  venv/bin/python scripts/check_runtime.py
else
  /opt/homebrew/opt/python@3.12/bin/python3.12 scripts/check_runtime.py
fi

echo ""
read "?按回车关闭..."
