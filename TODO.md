# Qwensper 待办

产品级 backlog，与 [docs/dev-plan.md](docs/dev-plan.md) 的 M1–M7 里程碑分开维护。完成某项后把 `- [ ]` 改成 `- [x]` 并注明日期。

---

## 功能

### 翻译 + 专业词库（Qwen3 4B）

- [ ] **逐字稿/总结双语导出**：在任务详情页增加「翻译」操作，支持中↔英（及后续扩展语言）；译文与原文分段对齐，可单独导出 Markdown / JSON。
- [ ] **专业词库（Glossary）**：
  - 设置页维护词库：词条（源语言）、首选译法、可选备注/领域标签。
  - 支持项目级默认词库 + 单任务覆盖（例如某次法律访谈导入专用术语表）。
  - 词库持久化到本地 JSON（如 `outputs/glossaries/`），完全离线，不上传。
- [ ] **翻译引擎**：复用现有 Ollama 栈，默认模型 **`qwen3:4b`**（与总结 / digest 一致）；`ollama pull qwen3:4b` 已在 README 与 `/api/health` 检查中覆盖。
  - 新建 `local_transcriber/translate.py`（或扩展现有 `chat.py`）：按 segment 或按 chunk 调用，prompt 中注入词库条目，要求专有名词严格遵循词库。
  - 长逐字稿分块翻译，避免超出 4B 上下文；块边界尽量落在发言人段落之间。
- [ ] **API / UI**：
  - `POST /api/tasks/{id}/translate`（目标语言、是否使用词库 ID）
  - 任务对象增加 `translations` 或独立侧车文件路径；详情页 Tab 或折叠区展示「原文 | 译文」。
- [ ] **验收**：60 秒样本 + 含 5–10 条专业术语的词库 → 译文中术语一致；完全离线模式下仍可翻译（仅依赖本地 Ollama）。

### 长音频（3–4 小时）

- [ ] 在 `pipeline.py` 前增加显式 **pre-chunker**（参考 [docs/long-audio-chunking-research.md](docs/long-audio-chunking-research.md)），段级进度写入 SQLite，支持中断后续跑。
- [ ] 任务列表展示「第 N/M 段」粗粒度 ETA。

### 详情页增强（低优先级）

- [ ] 可选：内嵌音频播放器（frontend-spec 曾标为 MVP 不做，按需 reopen）。
- [ ] 时间线 Tab（发言人轨道可视化，D4 曾锁定不做）。

---

## 工程 / 质量

- [ ] 为翻译与词库 API 补充 `pytest`（CRUD 词库、mock Ollama 返回、术语是否出现在 prompt）。
- [ ] 更新 README「已有能力」表与设置页模型说明（列出翻译依赖 `qwen3:4b`）。

---

## 明确不做（备忘）

- 云端翻译 API / 在线术语服务
- npm 前端构建
- 实时录音转录
