#!/bin/zsh
# Liasse launcher — runs inside Contents/MacOS/ of the .app bundle.
# 流程（v0.2.x）:
#   1. 找 Python 3.12 / 建 venv（首次启动 5-10 秒）
#   2. 装 requirements-bootstrap.txt（轻量集，30-60 秒）→ UI 能起来
#   3. 立即 exec launch_app.py，让用户看到界面
#   4. 同步在后台 pip install requirements-mlx.txt（5-10 GB，~30 分钟）
#      前端通过 /api/install/progress 显示进度，装完自动解锁上传按钮
set -e

APP_BUNDLE="$(cd "$(dirname "$0")/.."; pwd)"
RESOURCES="$APP_BUNDLE/Resources"
APP_DIR="$RESOURCES/app"
LOG_DIR="$HOME/Library/Logs/Liasse"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/launcher.log"
INSTALL_LOG="$LOG_DIR/install.log"
exec >>"$LOG" 2>&1
echo ""
echo "==== launch $(date -u +'%Y-%m-%dT%H:%M:%SZ') ===="
echo "APP_DIR=$APP_DIR"

if [ ! -d "$APP_DIR" ]; then
  /usr/bin/osascript -e 'display alert "Liasse 安装文件损坏" message "找不到内置的 app 目录，请重新下载 .dmg。" as critical buttons {"好"} default button "好"'
  exit 1
fi

cd "$APP_DIR"

# 让所有 HF 模型缓存到 .app 旁边的固定目录（首次安装时 0.6B 已经预先放进来）
export HF_HOME="$APP_DIR/.hf_cache"
mkdir -p "$HF_HOME"

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

# 阶段 1：保证 venv 存在 + bootstrap 已装
NEEDS_BOOTSTRAP=0
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  PYTHON_BIN="$(choose_python)"
  if [ -z "$PYTHON_BIN" ]; then
    /usr/bin/osascript <<'OSA'
display alert "需要 Python 3.12" message "Liasse 第一次启动需要 Python 3.12 来安装依赖。请先在终端运行：

  brew install python@3.12

装好后重新打开 Liasse。" as critical buttons {"好"} default button "好"
OSA
    exit 1
  fi
  echo "首次启动：用 $PYTHON_BIN 建 venv"
  /usr/bin/osascript -e 'display notification "正在准备运行环境（约 1 分钟），完成后界面会自动打开…" with title "Liasse"' || true
  "$PYTHON_BIN" -m venv "$APP_DIR/venv"
  "$APP_DIR/venv/bin/python" -m pip install --upgrade pip wheel
  NEEDS_BOOTSTRAP=1
fi

# 检查 bootstrap 集是否齐（探一两个代表性的包）
if ! "$APP_DIR/venv/bin/python" -c "import fastapi, uvicorn, webview" 2>/dev/null; then
  NEEDS_BOOTSTRAP=1
fi

if [ "$NEEDS_BOOTSTRAP" = "1" ]; then
  echo "装 bootstrap（轻量集）..."
  "$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/requirements-bootstrap.txt" 2>&1 | tee -a "$INSTALL_LOG"
fi

# 阶段 2：核心 ASR 引擎没装好 → 后台装，前端会显示进度
if ! "$APP_DIR/venv/bin/python" -c "import mlx_qwen3_asr" 2>/dev/null; then
  echo "后台装核心 ASR 引擎（5-10 GB，约 20-40 分钟）..."
  # 先清空 install.log 让 /api/install/progress 看到的是这次的进度
  : > "$INSTALL_LOG"
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] 开始安装核心运行环境" >> "$INSTALL_LOG"
  nohup "$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/requirements-mlx.txt" \
    >> "$INSTALL_LOG" 2>&1 &
  INSTALL_PID=$!
  echo "$INSTALL_PID" > "$APP_DIR/.install-pid"
  echo "后台 pip pid=$INSTALL_PID, log=$INSTALL_LOG"
fi

# 提示 ollama
if ! curl -s --max-time 1 --noproxy '*' http://127.0.0.1:11434/api/tags > /dev/null 2>&1; then
  /usr/bin/osascript -e 'display notification "Ollama 没在运行。总结和 AI Chat 需要它。可以在终端运行 ollama serve 或 brew services start ollama。" with title "Liasse"' || true
fi

exec "$APP_DIR/venv/bin/python" "$APP_DIR/launch_app.py"
