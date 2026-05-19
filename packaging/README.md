# 打包 Liasse.dmg

构建一个可双击打开的 macOS .app + .dmg。配合 in-app 的「需要下载模型」对话框，用户首次启动后会被引导下载 pyannote 和 qwen3:4b。

## 一键构建

```bash
./packaging/build_dmg.sh
```

产物在 `dist/Liasse-<version>.dmg`。

默认行为：
- 把项目源码 + `Start Liasse.command` + `launch_app.py` + `local_transcriber/` 整个拷进 `.app/Contents/Resources/app/`
- 排除 `.env` / `outputs/` / `tests/` / `docs/` / `vendor/` / `venv/` / `CLAUDE.md` / `.claude/` 等内部文件
- 把 **Qwen3-ASR 0.6B** 和 **Qwen3-ForcedAligner 0.6B** 模型（共约 3.5 GB）从本机 `~/.cache/huggingface/hub/` 复制到 `.app/Contents/Resources/app/.hf_cache/hub/`
- 调 `hdiutil create` 生成 UDZO 压缩的 .dmg

最终大小：约 **3 GB**。

## 控制选项

| 变量 | 默认 | 说明 |
|---|---|---|
| `INCLUDE_ASR_06B` | `1` | 1=捆绑 0.6B ASR；0=不捆，用户首次用时下载 |
| `INCLUDE_FORCED_ALIGNER` | `1` | 1=捆绑 ForcedAligner；0=不捆，但自动分段会失败 |

最小化 .dmg（仅源码，~100 KB）—— 调试用：

```bash
INCLUDE_ASR_06B=0 INCLUDE_FORCED_ALIGNER=0 ./packaging/build_dmg.sh
```

不捆绑模型的 .dmg（约 50 MB，用户首次启动后再下）：

```bash
INCLUDE_ASR_06B=0 ./packaging/build_dmg.sh
```

## 用户首次启动流程

1. 双击 `.dmg` → 拖 `Liasse.app` 到 `Applications/`
2. 首次右键 → 打开（绕过 Gatekeeper，因为没签名）。系统弹「来自未知开发者」确认一次即可
3. 第一次启动会触发 `launcher.sh`：
   - 检查 `Applications/Liasse.app/Contents/Resources/app/venv/`
   - 没有就用系统的 Python 3.12（推荐 `brew install python@3.12`）建一个，再装 `requirements-mlx.txt`
   - 这一步约 3-5 分钟，期间用 `osascript` 弹通知告诉用户
4. 启动 `launch_app.py`，pywebview 窗口出现
5. 用户在 UI 里点「发言人识别」「生成总结」「AI Chat」其中一个 → 检测到对应模型未下载 → 弹「需要下载模型」对话框，提供 copy-able 命令
6. 用户去终端跑命令（`ollama pull qwen3:4b` 或 `snapshot_download(...)`），回 App 点「重新检查」按钮

## 已知限制

- **没有代码签名 / 公证**。Gatekeeper 会拦一次（用户右键→打开）。要做 notarization 需要 Apple Developer ID 证书 + `notarytool`，超出 MVP 范围。
- **依赖系统 Python 3.12**。首次启动前用户必须 `brew install python@3.12`，否则 launcher 会弹 alert 让他去装。
- **HF token**：pyannote 需要用户在 `~/.cache/huggingface/token` 或环境变量里有 HF_TOKEN。launcher 不主动配置，用户得在终端跑过一次 `huggingface-cli login`。
- **重定位 venv 问题**：venv 是在用户机器上建的，不存在跨机器复制。`.app` 本身可以跨机器拷贝，但 `Contents/Resources/app/venv/` 必须在目标机器重新建。`launcher.sh` 已处理。
- **iCloud Drive 路径**：如果用户把 `.app` 放在 iCloud Drive 而不是 `Applications/`，里面的 `venv/.pth` 会被 Python 3.13+ 忽略（用 3.12 没问题，但仍然要避免）。

## 进阶：完全无 venv 的打包

如果想做一个无需用户预装 Python 的 .app，需要：

1. PyInstaller 把整个 venv + Python 解释器塞进 .app（约 +500 MB）
2. 解决 MLX、torch、pyannote 的 native 库引用问题（PyInstaller 的 hooks 不够全，得手动写 spec 文件）
3. 处理 spawn-context 子进程（multiprocessing 在 frozen 环境里需要特殊配置）

预估额外开发量 2-3 天。目前的 launcher.sh 是更轻的 MVP 路径。

## 验收命令

```bash
# 1. 干净跑一次（不含模型，最快）
INCLUDE_ASR_06B=0 INCLUDE_FORCED_ALIGNER=0 ./packaging/build_dmg.sh

# 2. plutil 校验
plutil -lint build/Liasse.app/Contents/Info.plist

# 3. 列 .app 内容确认没有 .env / CLAUDE.md
find build/Liasse.app -name '.env' -o -name 'CLAUDE.md' -o -name '.claude'

# 4. mount .dmg 检查
hdiutil attach dist/Liasse-0.2.0.dmg -nobrowse -mountpoint /tmp/wq_mount
ls /tmp/wq_mount/
hdiutil detach /tmp/wq_mount
```
