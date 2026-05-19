#!/bin/zsh
# 从源码构建 WhisperQwen.app 和 WhisperQwen-<version>.dmg
# 默认会把 Qwen3-ASR-0.6B 模型一起塞进 .app（约 1.2 GB），
# pyannote / qwen3:4b 在 App 内通过弹窗指引用户首次启动后再下。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.."; pwd)"
PKG="$ROOT/packaging"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
APP_NAME="WhisperQwen"
VERSION="0.2.0"
APP_BUNDLE="$BUILD/$APP_NAME.app"

INCLUDE_ASR_06B="${INCLUDE_ASR_06B:-1}"        # 1=默认捆绑 0.6B；0=跳过（更小的 .dmg）
INCLUDE_FORCED_ALIGNER="${INCLUDE_FORCED_ALIGNER:-1}"

echo "[1/6] 清理旧的 build/ 和 dist/"
rm -rf "$BUILD"
mkdir -p "$BUILD" "$DIST"

echo "[2/6] 创建 .app skeleton"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources/app"
cp "$PKG/Info.plist" "$APP_BUNDLE/Contents/Info.plist"
cp "$PKG/launcher.sh" "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
chmod +x "$APP_BUNDLE/Contents/MacOS/$APP_NAME"

echo "[3/6] 拷贝项目源码 → Resources/app/"
RES_APP="$APP_BUNDLE/Contents/Resources/app"

# 项目源码（去掉 venv / outputs / 大文件）
rsync -a \
  --exclude 'venv/' \
  --exclude '.venv*/' \
  --exclude 'outputs/' \
  --exclude 'test_audio/' \
  --exclude 'vendor/' \
  --exclude 'build/' \
  --exclude 'dist/' \
  --exclude 'front_end_prototype.png' \
  --exclude '.git/' \
  --exclude '.DS_Store' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'packaging/' \
  --exclude '.env' \
  --exclude '.env.*' \
  --exclude '.claude/' \
  --exclude '.pytest_cache/' \
  --exclude 'CLAUDE.md' \
  --exclude 'design.md' \
  --exclude 'docs/' \
  --exclude 'tests/' \
  --exclude 'scripts/' \
  --exclude 'run_app.py' \
  --exclude 'Run Test Audio.command' \
  --exclude 'Setup MLX Test Env.command' \
  --exclude 'Start Local Transcriber.command' \
  --exclude 'Check Runtime.command' \
  "$ROOT/" "$RES_APP/"

echo "[4/6] 内置 Qwen3-ASR-0.6B 模型（用户机器 ~/.cache/huggingface/hub 已存在的话）"
HF_HUB="$HOME/.cache/huggingface/hub"
APP_HF_HUB="$RES_APP/.hf_cache/hub"
mkdir -p "$APP_HF_HUB"

bundle_model() {
  local repo_dir="$1"
  local label="$2"
  if [ -d "$HF_HUB/$repo_dir" ]; then
    echo "    ✓ 捆绑 $label"
    rsync -a "$HF_HUB/$repo_dir/" "$APP_HF_HUB/$repo_dir/"
  else
    echo "    ! 跳过 $label (本机未下载 — 用户首次启动会被引导)"
  fi
}

if [ "$INCLUDE_ASR_06B" = "1" ]; then
  bundle_model "models--Qwen--Qwen3-ASR-0.6B" "Qwen3-ASR 0.6B"
fi
if [ "$INCLUDE_FORCED_ALIGNER" = "1" ]; then
  bundle_model "models--Qwen--Qwen3-ForcedAligner-0.6B" "Qwen3 ForcedAligner 0.6B"
fi

# 不捆绑 pyannote（许可证要求用户单独同意） / 不捆绑 ollama 模型（不在 HF cache 里）

echo "[5/6] 生成 .dmg（容量 = $(du -sh "$APP_BUNDLE" | awk '{print $1}')）"
DMG_NAME="$APP_NAME-$VERSION.dmg"
DMG_PATH="$DIST/$DMG_NAME"
DMG_STAGE="$BUILD/dmg_stage"
mkdir -p "$DMG_STAGE"
cp -R "$APP_BUNDLE" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"

rm -f "$DMG_PATH"
hdiutil create \
  -volname "$APP_NAME $VERSION" \
  -srcfolder "$DMG_STAGE" \
  -ov \
  -format UDZO \
  -fs HFS+ \
  "$DMG_PATH"

echo "[6/6] 完成"
echo "  -> $DMG_PATH ($(du -sh "$DMG_PATH" | awk '{print $1}'))"
echo ""
echo "下一步："
echo "  - 用户双击 .dmg 后，把 WhisperQwen.app 拖进 Applications"
echo "  - 第一次右键 → 打开（绕过 Gatekeeper，因为没签名）"
echo "  - 首次启动 launcher.sh 会用 Python 3.12 建 venv，约 3-5 分钟"
echo "  - 之后 pyannote / qwen3:4b 在 App 里通过「需要下载模型」对话框引导用户安装"
