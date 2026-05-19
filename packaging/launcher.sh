#!/bin/zsh
# WhisperQwen launcher — runs inside Contents/MacOS/ of the .app bundle.
# Responsibilities:
#   1. Locate Contents/Resources/app (the project source)
#   2. On first launch, build the venv from Python 3.12
#   3. Hand off to launch_app.py via pywebview
set -e

APP_BUNDLE="$(cd "$(dirname "$0")/.."; pwd)"
RESOURCES="$APP_BUNDLE/Resources"
APP_DIR="$RESOURCES/app"
LOG_DIR="$HOME/Library/Logs/WhisperQwen"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/launcher.log"
exec >>"$LOG" 2>&1
echo ""
echo "==== launch $(date -u +'%Y-%m-%dT%H:%M:%SZ') ===="
echo "APP_DIR=$APP_DIR"

if [ ! -d "$APP_DIR" ]; then
  /usr/bin/osascript -e 'display alert "WhisperQwen 安装文件损坏" message "找不到内置的 app 目录，请重新下载 .dmg。" as critical buttons {"好"} default button "好"'
  exit 1
fi

cd "$APP_DIR"

# 让所有 HF 模型缓存到 .app 旁边的固定目录（首次安装时 0.6B 已经预先放进来）
export HF_HOME="$APP_DIR/.hf_cache"
mkdir -p "$HF_HOME"

# 找一个可用的 Python 3.12
choose_python() {
  for candidate in \
    "$APP_DIR/venv/bin/python" \
    "/opt/homebrew/opt/python@3.12/bin/python3.12" \
    "/usr/local/opt/python@3.12/bin/python3.12" \
    "/opt/homebrew/bin/python3.12" \
    "/usr/local/bin/python3.12" \
    "python3.12"
  do
    if command -v "$candidate" >/dev/null 2>&1; then
      ver="$("$candidate" -c 'import sys; print(sys.version_info[:2])' 2>/dev/null || true)"
      case "$ver" in
        "(3, 12)") echo "$candidate"; return 0 ;;
      esac
    fi
  done
  return 1
}

if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  PYTHON_BIN="$(choose_python)"
  if [ -z "$PYTHON_BIN" ]; then
    /usr/bin/osascript <<'OSA'
display alert "需要 Python 3.12" message "WhisperQwen 第一次启动需要 Python 3.12 来安装依赖。请先在终端运行：

  brew install python@3.12

装好后重新打开 WhisperQwen。" as critical buttons {"好"} default button "好"
OSA
    exit 1
  fi
  echo "首次启动：用 $PYTHON_BIN 建 venv"

  /usr/bin/osascript -e 'display notification "首次启动正在安装运行环境，约 3-5 分钟…" with title "WhisperQwen"' || true

  "$PYTHON_BIN" -m venv "$APP_DIR/venv"
  "$APP_DIR/venv/bin/python" -m pip install --upgrade pip wheel
  "$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/requirements-mlx.txt"
fi

# 提示 ollama
if ! curl -s --max-time 1 --noproxy '*' http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
  /usr/bin/osascript -e 'display notification "Ollama 没在运行。总结和 AI Chat 需要它。可以在终端运行 ollama serve 或 brew services start ollama。" with title "WhisperQwen"' || true
fi

exec "$APP_DIR/venv/bin/python" "$APP_DIR/launch_app.py"
