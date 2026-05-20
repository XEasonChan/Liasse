# Qwensper 待办

产品级 backlog，与 [docs/dev-plan.md](docs/dev-plan.md) 的 M1–M7 里程碑分开维护。完成某项后把 `- [ ]` 改成 `- [x]` 并注明日期。

**优先级**：P0 = 影响日常可用 / 必须修；P1 = 主要新功能；P2 = 体验改善与基建。

每项标记 → **[plan](docs/superpowers/plans/...)** 指向详细研发计划。所有 plan 写于 `docs/superpowers/plans/2026-05-19-*.md`。Roadmap：[docs/superpowers/plans/2026-05-19-roadmap.md](docs/superpowers/plans/2026-05-19-roadmap.md)。

---

## 已知 bug

- **Speaker alignment：长 ASR segment + 细粒度 pyannote turn 不匹配**（2026-05-19 已修，commit `alignment.py` 加权 overlap 算法 + `tests/test_alignment.py` 回归）

---

## P0 — 修补类（合并为一个 plan）

→ [plan-p0-housekeeping.md](docs/superpowers/plans/2026-05-19-plan-p0-housekeeping.md)（已执行 2026-05-19）

- **摘要 / 总结「重新生成」UI 入口**（2026-05-19 验证已存在）— `task-detail.js:191-204` 的 `regenerateSummary` + `:summaryRegen / summaryGen` 文案早已实现，端点 `routers/qa.py::regenerate_summary` 存在。这是 BUILD_REPORT 过期 TODO。
- **删除任务时同步清理上传副本**（2026-05-19 修复）— `liasse/web_app.py::delete_task` 加 `is_relative_to(uploaded_audio)` 路径白名单后 unlink；`tests/test_web_api.py` 加 2 个回归（删副本 + 不动原生路径 + 默认 `delete_outputs=false` 保留）。
- ~~**BM25 索引在用户编辑后自动失效重建**~~（误诊，撤销）— `qa_engine.build_index_for_task` 没有缓存，每次都重建。无失效问题。

---

## P1 — 翻译 + 专业词库（Qwen3 4B）

→ [plan-p1a-translation-and-glossary.md](docs/superpowers/plans/2026-05-19-plan-p1a-translation-and-glossary.md)

✅ **完成（2026-05-19）** — backend + UI + 双语 MD 导出全部落地，pytest 215 passed。

- [x] **逐字稿/总结双语导出**：详情页 translate-toolbar 含目标语言、词库选择、翻译按钮、视图切换、导出双语；译文与原文 segment 对齐；导出 Markdown。
- [x] **专业词库（Glossary）**：设置页 CRUD 编辑器；持久化 `outputs/glossaries/<name>.json`，原子写。
- [x] **翻译引擎 `liasse/translate.py`**：`qwen3:4b` 默认，batch_size=20；prompt 注入词库 + JSON 修复抓最外层 {...} 块。
- [x] **API**：`/api/glossaries[/<name>]` CRUD + `POST /api/tasks/:id/translate` + `GET /api/tasks/:id/export-bilingual`。
- [x] **测试**：tests/test_glossary_store.py 7 个、tests/test_translate.py 9 个、tests/test_translation_api.py 12 个、tests/test_translation_persistence.py 3 个、tests/test_exporters_bilingual.py 3 个。

---

## P1 — 长音频 pre-chunker

→ [plan-p1b-long-audio-prechunker.md](docs/superpowers/plans/2026-05-19-plan-p1b-long-audio-prechunker.md)

- **音频预切分模块 `liasse/audio_chunker.py`**：silero-vad cut + 25-30min merge；fallback 到 ffmpeg 等长 30min 切片。
- **TaskRow 加 `chunks` 列**：段级状态 `queued | running | done | failed`，可恢复。
- **改造 `transcribe_pipeline.py`**：超过 `preChunkerMinSeconds` 阈值时按段循环；进度按段加 `chunk_completed` 消息。
- **任务列表 / 详情页 UI**：显示「第 X/N 段 · 段内 Y%」；retry 时只重跑未完成段。
- **pyannote 跑完整音频后映射回 chunk**（保 speaker 全局一致）。
- **测试**：silero / ffmpeg 切分单测；60s 短样不切；30min 样本切 1-2 段；resume 测试。

---

## P1 — 主要功能Roadmap

- **mention 模型 + 资料查询和对话** → [plan-p1c-mention-models-and-chat.md](docs/superpowers/plans/2026-05-19-plan-p1c-mention-models-and-chat.md)（plan 完成，未实现）
- **支持导出pdf** → [plan-p1d-pdf-export.md](docs/superpowers/plans/2026-05-19-plan-p1d-pdf-export.md)（plan 完成，未实现）

---

## P2 — 体验与基建

→ [plan-p2-polish.md](docs/superpowers/plans/2026-05-19-plan-p2-polish.md)（下一轮细化）

- **1.7B ASR 模型一键下载入口**：settings「模型管理」加 row + 调已有 `downloader.py` SSE，model-required-modal 复用。
- **模型版本 health 自检**：`/api/health` 加 pyannote 4.x / mlx-qwen3-asr / qwen3:4b 版本字段；版本变化时提示用户。
- **README「已有能力」表**：列出翻译能力、长音频段级恢复、词库；列出依赖模型清单（含 qwen3:4b）。
- **设置页模型说明**：翻译依赖 `qwen3:4b`，长音频建议 silero-vad，pyannote 4.x speaker-diarization-community-1 等。
- **「打开日志」按钮**：当前 alert，应该走 `POST /api/open-path` 真实打开 Finder/对应文件。
- **详情页「批量改名/合并段」**：M5 遗留 — 当前只能逐段编辑文字，发言人改名仅在「逐字稿」头点开。

---

## P3 — 明确不做

- 详情页内嵌音频播放器（D3 锁定）
- 时间线 Tab（D4 锁定）
- 云端翻译 API / 在线术语服务
- npm 前端构建步骤
- 实时录音转录
- 用户账号 / 协作 / 服务器部署

---

## 完成度参考

- ✅ 2026-05-18 — M1-M7 全部完成（首版重写）
- ✅ 2026-05-18 — UX 改造（路径化上传 + 状态机 + 依赖弹窗 + 15 个 todo）
- ✅ 2026-05-19 — visibility（heartbeat ETA）+ i18n 三语 + 中断恢复 + 模型评估
- ✅ 2026-05-19 — cleanup pass（拆 routers/services、删 chat.py + summarizer.py 双轨、单元测试 126 passed）
- ✅ 2026-05-19 — pyannote 与 ASR 并行（精确模式 ≈ ASR 时长）
- ✅ 2026-05-19 — alignment bug 修复（加权 overlap）
- ✅ 2026-05-19 — 上传区配置简化 + 主 CTA 放大（onboarding 动线）

