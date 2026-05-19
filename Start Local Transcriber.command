#!/bin/zsh
# 旧入口，已被 Start WhisperQwen.command 取代。保留是为了避免 macOS 工作流挂载文件不见。
cd "$(dirname "$0")"
echo "[Start Local Transcriber] 已弃用，请改用 Start WhisperQwen.command。"
echo "正在自动切换..."
exec ./"Start WhisperQwen.command"
