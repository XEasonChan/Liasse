#!/bin/zsh
# Liasse 安装助手
# 这个脚本住在 DMG 里。双击它会：
#   1. 把 Liasse.app 拷到 /Applications/
#   2. 移除 macOS quarantine 标记（不然 macOS Sequoia 不让打开）
#   3. 启动 Liasse
#
# 为什么需要这个：Liasse 没有 Apple Developer ID 签名（开源项目不付 $99/年），
# 在 macOS 15+ 上默认会被 Gatekeeper 直接拦死（弹窗只有"完成"按钮）。
# 这个脚本走 xattr 路径把 quarantine 干掉，比让用户去 System Settings 里点
# "仍要打开"更顺。

set -e

DMG_DIR="$(cd "$(dirname "$0")"; pwd)"
SRC_APP="$DMG_DIR/Liasse.app"
DEST="/Applications/Liasse.app"

clear
echo "===================================="
echo "  Liasse — 本地访谈转录工具"
echo "  安装助手"
echo "===================================="
echo ""

if [ ! -d "$SRC_APP" ]; then
  /usr/bin/osascript -e 'display alert "找不到 Liasse.app" message "请确认你是从挂载的 Liasse.dmg 里运行这个脚本。" as critical buttons {"好"} default button "好"'
  exit 1
fi

if [ -d "$DEST" ]; then
  echo "→ 检测到已安装的 Liasse.app，先停掉旧进程..."
  pkill -f "/Applications/Liasse.app/Contents/MacOS/Liasse" 2>/dev/null || true
  echo "→ 移除旧版..."
  rm -rf "$DEST"
fi

echo "→ 复制 Liasse.app 到 /Applications/"
cp -R "$SRC_APP" "$DEST"

echo "→ 移除 macOS quarantine 标记（绕过 Gatekeeper 未签名拦截）"
/usr/bin/xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true

echo "→ 启动 Liasse"
open "$DEST"

echo ""
echo "✓ 安装完成。"
echo ""
echo "下一步："
echo "  - 首次启动 launcher.sh 会自动建 Python venv（需要 brew Python 3.12，"
echo "    没装的话会弹窗提示）。"
echo "  - 模型在 App 内通过\"需要下载模型\"对话框引导下载。"
echo "  - 启动日志：~/Library/Logs/Liasse/launch.log"
echo ""
echo "这个 Terminal 窗口可以关掉了。"
echo ""
