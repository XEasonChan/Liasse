#!/bin/zsh
# 从源码构建 Liasse.app 和 Liasse-<version>.dmg
# 默认会把 Qwen3-ASR-0.6B 模型一起塞进 .app（约 1.2 GB），
# pyannote / qwen3:4b 在 App 内通过弹窗指引用户首次启动后再下。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.."; pwd)"
PKG="$ROOT/packaging"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
APP_NAME="Liasse"
VERSION="0.2.2"
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
cp "$ROOT/liasse/web_static/assets/app-icon.icns" "$APP_BUNDLE/Contents/Resources/AppIcon.icns"
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
  --exclude 'Run Test Audio.command' \
  --exclude 'Setup MLX Test Env.command' \
  --exclude 'Check Runtime.command' \
  --exclude 'TODO.md' \
  --exclude 'TODO_*.md' \
  --exclude 'AGENTS.md' \
  --exclude 'ARCHITECTURE.md' \
  --exclude '*.egg-info/' \
  --exclude 'reference/' \
  "$ROOT/" "$RES_APP/"

echo "[4/6] 内置 Qwen3-ASR-0.6B 模型（用户机器 ~/.cache/huggingface/hub 已存在的话）"
HF_HUB="$HOME/.cache/huggingface/hub"
APP_HF_HUB="$RES_APP/.hf_cache/hub"
mkdir -p "$APP_HF_HUB"

bundle_model() {
  local repo_dir="$1"
  local label="$2"
  local repo_id="$3"
  if [ -d "$HF_HUB/$repo_dir" ]; then
    echo "    ✓ 捆绑 $label"
    rsync -a "$HF_HUB/$repo_dir/" "$APP_HF_HUB/$repo_dir/"
  else
    echo ""
    echo "ERROR: 本机没有 $label ($HF_HUB/$repo_dir)"
    echo "       捆绑该模型是默认行为。先在本机下载它："
    echo ""
    echo "         venv/bin/python -c \"from huggingface_hub import snapshot_download; snapshot_download('$repo_id')\""
    echo ""
    echo "       或者设置 INCLUDE_ASR_06B=0 / INCLUDE_FORCED_ALIGNER=0 来主动跳过。"
    exit 2
  fi
}

if [ "$INCLUDE_ASR_06B" = "1" ]; then
  bundle_model "models--Qwen--Qwen3-ASR-0.6B" "Qwen3-ASR 0.6B" "Qwen/Qwen3-ASR-0.6B"
fi
if [ "$INCLUDE_FORCED_ALIGNER" = "1" ]; then
  bundle_model "models--Qwen--Qwen3-ForcedAligner-0.6B" "Qwen3 ForcedAligner 0.6B" "Qwen/Qwen3-ForcedAligner-0.6B"
fi

# 不捆绑 pyannote（许可证要求用户单独同意） / 不捆绑 ollama 模型（不在 HF cache 里）

echo "[5/6] 生成 .dmg（容量 = $(du -sh "$APP_BUNDLE" | awk '{print $1}')）"
DMG_NAME="$APP_NAME-$VERSION.dmg"
DMG_PATH="$DIST/$DMG_NAME"
DMG_STAGE="$BUILD/dmg_stage"
mkdir -p "$DMG_STAGE"
cp -R "$APP_BUNDLE" "$DMG_STAGE/"
ln -s /Applications "$DMG_STAGE/Applications"
# 助手脚本：双击就完成 复制 + xattr 去 quarantine + 启动 三件套
# macOS 15 Sequoia 起，未签名 .app 不能再右键→打开绕过 Gatekeeper
cp "$PKG/install.command" "$DMG_STAGE/双击安装 Liasse.command"
chmod +x "$DMG_STAGE/双击安装 Liasse.command"

# DMG 根目录的 README（解释为什么要点助手脚本）
cat > "$DMG_STAGE/README.txt" <<'EOF'
Liasse — 本地访谈转录工具
==========================

【推荐】双击 "双击安装 Liasse.command"
   会自动把 Liasse 拷到 Applications/、绕过 macOS Gatekeeper、启动。

【手动方式】
   1. 拖 Liasse.app 到 Applications/
   2. 打开 Terminal，运行：
        xattr -dr com.apple.quarantine /Applications/Liasse.app
   3. 双击 /Applications/Liasse.app 启动

为什么需要这一步？
   Liasse 是开源项目，没有支付 Apple Developer Program 的 $99/年签名费用。
   macOS Sequoia (15+) 默认会拦下所有未签名 App，且不再允许"右键→打开"绕过。
   xattr 命令把 macOS 给下载文件加的 quarantine 标记拆掉，就能正常启动。

启动日志：~/Library/Logs/Liasse/launch.log
EOF

rm -f "$DMG_PATH"
hdiutil create \
  -volname "Liasse $VERSION — 双击安装" \
  -srcfolder "$DMG_STAGE" \
  -ov \
  -format UDZO \
  -fs HFS+ \
  "$DMG_PATH"

echo "[6/6] 完成"
echo "  -> $DMG_PATH ($(du -sh "$DMG_PATH" | awk '{print $1}'))"
echo ""
echo "下一步："
echo "  - 用户双击 .dmg，看到「双击安装 Liasse.command」"
echo "  - 双击该脚本 → Terminal 弹安全确认 → 点「打开」"
echo "  - 脚本自动拷贝 + xattr + 启动"
echo "  - 首次启动 launcher.sh 会用 Python 3.12 建 venv，约 3-5 分钟"
