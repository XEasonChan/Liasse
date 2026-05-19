#!/bin/zsh
cd "$(dirname "$0")"

# 使用 Python 3.12 而非 3.14：
#   3.13+ 会跳过 hidden 目录里的 .pth 文件，iCloud 又会自动给 .开头的目录加 hidden 标志。
#   venv 目录名不带 . 前缀 + Python 3.12 = 两边都绕开。
if [ -x "/opt/homebrew/opt/python@3.12/bin/python3.12" ]; then
  PYTHON_BIN="/opt/homebrew/opt/python@3.12/bin/python3.12"
elif [ -x "/opt/homebrew/bin/python3.12" ]; then
  PYTHON_BIN="/opt/homebrew/bin/python3.12"
else
  echo "没有找到 Python 3.12。请先 brew install python@3.12。"
  read "?按回车关闭..."
  exit 1
fi

echo "使用 $PYTHON_BIN 创建 venv/"
exit_code=0
"$PYTHON_BIN" -m venv venv || exit_code=$?

if [ "$exit_code" -eq 0 ]; then
  echo "安装基础桌面依赖。"
  venv/bin/python -m pip install -U pip setuptools wheel || exit_code=$?
fi

if [ "$exit_code" -eq 0 ]; then
  venv/bin/python -m pip install -r requirements-bootstrap.txt || exit_code=$?
fi

if [ "$exit_code" -eq 0 ]; then
  echo "安装 MLX/Qwen 转录依赖（PyPI 官方包）。这一步需要联网。"
  venv/bin/python -m pip install -r requirements-mlx.txt || exit_code=$?
fi

echo ""
if [ "$exit_code" -eq 0 ]; then
  echo "完成。现在可以运行 ./Check\\ Runtime.command，然后启动 ./Start\\ Liasse.command。"
else
  echo "安装失败，请看上面的错误信息。"
fi

if [ -t 0 ]; then
  read "?按回车关闭..."
fi
exit "$exit_code"
