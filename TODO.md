# Qwensper 待办

产品级 backlog，与 [docs/dev-plan.md](docs/dev-plan.md) 的 M1–M7 里程碑分开维护。完成某项后把 `- [ ]` 改成 `- [x]` 并注明日期。

---

## 已知 bug

### Speaker alignment：长 ASR segment + 细粒度 pyannote turn 不匹配

**现象**：`pyannote` 精细模式下，pyannote 正确识别出 2 个 speaker（36 + 16 turns），但
`alignment.assign_speakers` 把所有 ASR segments 都套成了 SPEAKER_00。

**根因**：ASR 给的 segments 通常 8-30 秒长，一段会跨越 5-10 个 pyannote 细 turn
(0.3-5 秒/个)。`assign_speakers` 的算法是「找单个 overlap 最长的 turn」，因为
SPEAKER_00 占总时长多，长 segment 跟它的最大单 turn 重叠总是赢。

**修复方向**：改 `alignment.py` 算法，按时间总量加权而不是单 turn 最长：
对每个 segment，遍历所有有 overlap 的 turn，按 speaker 累计 overlap 时长，
选累计最长的那个 speaker。或者：把长 ASR segment 按 pyannote turn 边界**拆细**，
再每小段独立分配 speaker（这条更优但要改 schema）。

**测试**：用 2 分钟双人样本（test_audio/cut-2min-mid.m4a，pyannote 输出
SPEAKER_00×36 + SPEAKER_01×16 turns）当 fixture，期望 alignment 后 segment
里也出现两个 speaker。

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
