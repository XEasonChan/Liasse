# Liasse · Architecture

> 给新接手这个仓库的人/agent 看的一份"30 分钟读完就能干活"的地图。
> 写于 2026-05-19，主要 cleanup pass 后；产品 rebrand 到 Liasse 后更新于同日。
>
> **命名约定**：
> - **产品名** = `Liasse`（用户看到的、品牌、UI、文档）
> - **工作目录 / repo 名** = `Qwensper`（历史保留，不动）
> - **Python 包** = `local_transcriber`（pending → `liasse`，独立 PR）
> - 内部模块名出现在 import / 路径里时仍是 `local_transcriber`，不是错。

## 一句话

本地访谈转录桌面应用：用户拖音频进去 → Qwen3-ASR 转文字 → 可选的发言人识别（声纹/LLM 文本/不做）→ 可选的 LLM 摘要 + RAG 问答。FastAPI 后端 + pywebview 桌面壳 + Vue 3 CDN 前端。**完全离线，IRB 合规**。

## 数据流

```
                 ┌────────────────────────────────────────────────────────┐
[音频文件]   ──▶ │ task_runner 子进程 (_worker_entry)                       │
   │             │   │                                                      │
   │             │   ├─ TranscribePipeline (transcribe_pipeline.py)          │
   │ HTTP POST   │   │   │                                                  │
   │ /api/tasks  │   │   ├─ mlx-qwen3-asr → chunk_completed × N             │
   │ /upload     │   │   │   每 chunk emit partial_transcript ───┐         │
   │             │   │   │                                       │         │
   ▼             │   │   ├─ pyannote diarization (可选, MPS)     │         │
[FastAPI]        │   │   │                                       │         │
[web_app.py]     │   │   └─ exporters → markdown/json/srt        │         │
   │             │   │                                           │         │
   │             │   ├─ speaker_labeler (可选, LLM 文本角色标注) │         │
   │             │   │                                           │         │
   │             │   └─ summary_pipeline.analyze (可选)          │         │
   │             │       │                                       │         │
   │             │       └─ L1 抽取 × N → L2 综合 → BM25 索引   │         │
   │             │                                                ▼         │
   │             │   progress_queue (mp.Queue) ─────────▶ _apply_partial   │
   │             │                                                          │
   └─────────────┴──── done msg ──▶ _finalize ──▶ TaskRow ──▶ /api/tasks/:id
                                                              ▲
                                                              │ poll
                                                       [Vue 3 前端]
                                                       transcript / chat
                                                       / summary / settings
```

## 关键交付物：每个阶段完成后留下什么

| 阶段 | 完成信号 | 留下的交付物 | 谁能消费 |
|------|---------|------------|---------|
| ASR chunk 完成 | mlx 触发 `chunk_completed` 事件 | `TaskRow.transcript = {segments, partial: True, rawText, rawTextPath}` + `outputs/<task>/<stem>-raw.partial.txt` 文本副本 | 前端立即可读（**这是修复"等 4 小时看不到"那个痛点的关键**） |
| ASR 全部完成 | `_transcribe` 返回 | `result.segments` 内存对象（speaker 都是 `SPEAKER_00`） | pipeline 继续走 diarization |
| pyannote diarization 完成 | `assign_speakers` 赋值 speaker 字段 | `result.segments`（带真实 speaker_turns） | exporters |
| LLM speaker labeling 完成 | `label_segments` 返回 | `result.segments` (speakers 改名 SPEAKER_00/01) + `suggestedSpeakerLabels` dict | task_runner 写入 edits.speakerLabels |
| exporters 完成 | pipeline.run 返回 | `outputs/<stem-timestamp>/{<stem>-transcript.md, .json, .srt}` | 用户可下载 |
| summary_pipeline 完成 | analyze 返回 AnalysisResult | `outputs/<task>/l1_results.sqlite` + `analysis.summary_markdown` 写入 `TaskRow.summary_text` + BM25 索引内存对象 | /chat 路由 + 前端 summary tab |
| 整任务完成 | _finalize 写库 | `TaskRow.status=done, transcript.partial=False, outputs.dir, ...` | 持久状态 |

> **关键不变量**：`_apply_partial_transcript` 只在 `status==running` 时写 transcript，防止迟到的 partial 覆盖最终结果。

## 目录结构

```
local_transcriber/                              # 后端 Python 包
├── web_app.py                  423 行 — FastAPI app 装配（lifespan / mount / include_router /
│                                          tasks CRUD 路由）
├── task_runner.py              655 行 — 单 worker 后台任务编排（mp.Process + progress_queue）
├── transcribe_pipeline.py      227 行 — ASR + diarization + 导出（纯转录流水线）
├── summary_pipeline.py         229 行 — L1/L2 分层摘要 + BM25 索引（独立）
├── hierarchical_summary.py     211 行 — L1 抽取 / L2 综合的 prompt + Ollama 调用
├── asr.py                      490 行 — 4 个 ASR backend（mlx/qwen/whisper/demo）+ MLX patch
├── diarization.py               56 行 — PyannoteDiarizer wrapper
├── speaker_labeler.py          253 行 — LLM 文本语义角色标注（speakerMode=llm 时用）
├── alignment.py                 78 行 — segment ↔ speaker_turn 对齐
├── exporters.py                 81 行 — markdown / json / srt 导出
├── qa_engine.py                110 行 — QAEngine：BM25 检索 + Ollama 流式问答
├── transcript_index.py         133 行 — BM25 索引（含 jieba 分词）+ SQLite 持久化
├── transcript_chunker.py       161 行 — 访谈分块（含 VibeVoice 借鉴的 overlap 选项）
├── downloader.py               258 行 — HF snapshot_download 后台任务 + SSE
├── ollama_lifecycle.py         110 行 — Ollama HTTP client + loaded_model 上下文管理
├── model_router.py              70 行 — TaskKind → model 路由（4b/8b 按内存档自动选）
├── memory_monitor.py            50 行 — MemoryBudget 检测（tight/comfortable 档）
├── settings_store.py            63 行 — outputs/settings.json 读写
├── models.py                    79 行 — TranscriptSegment / SpeakerTurn / TranscriptionJob /
│                                          PipelineResult / SummaryResult dataclasses
├── db.py                       111 行 — SQLAlchemy ORM (TaskRow + Base + init_db /
│                                          session_scope)
├── schemas.py                   82 行 — Pydantic 请求/响应 + TaskConfig + speakerMode
│                                          validator
├── hf_paths.py                  ~28 行 — HF_HOME-aware 缓存路径助手
├── timefmt.py                   29 行 — format_clock / format_srt_time
├── routers/                    域路由（每个一个 APIRouter）
│   ├── __init__.py
│   ├── health.py                84 行 — /api/health, /api/install/progress
│   ├── models_routes.py        210 行 — /api/models, /api/models/download/*,
│   │                                       /api/ollama/start
│   └── qa.py                   143 行 — /api/tasks/:id/summary, /api/tasks/:id/chat
├── services/                   纯函数业务逻辑
│   ├── __init__.py
│   ├── ollama_health.py         35 行 — check_ollama, check_ollama_model
│   ├── model_cache.py           77 行 — check_model_cache, check_runtime_ready,
│   │                                       read_install_progress
│   └── fs_helpers.py            48 行 — unique_path, probe_audio_duration
├── cli.py                       58 行 — `qwensper-cli` 批处理入口
└── web_static/                 前端（Vue 3 CDN，无构建步骤）
    ├── index.html
    ├── app.js                  — 路由 + 全局状态
    ├── i18n.js + locales/{zh,en,es}.js
    ├── style.css
    └── components/             — task-list, task-detail, upload-zone, settings-page,
                                  chat-panel, statusbar, sidebar, toast, ...
```

## 抽象边界（谁依赖谁）

```
                    cli.py            launch_app.py
                       │                    │
                       ▼                    ▼
   ┌─────────────────────────────────────────────────────┐
   │  web_app.py  ←  routers/{health,models_routes,qa}   │
   └─────────────────────────────────────────────────────┘
              │                            │
              ▼                            ▼
        task_runner.py            services/{ollama,cache,fs}
              │
   ┌──────────┴────────────┐
   ▼                       ▼
transcribe_pipeline.py   summary_pipeline.py ──▶ qa_engine.py
   │                       │                          │
   ├─ asr.py               ├─ hierarchical_summary    └─ transcript_index.py
   ├─ diarization.py       ├─ transcript_chunker         (BM25)
   ├─ alignment.py         └─ model_router/budget
   ├─ exporters.py
   └─ speaker_labeler.py

      底层：models.py (dataclasses) · db.py (ORM) · schemas.py (Pydantic) ·
            ollama_lifecycle · memory_monitor · timefmt · hf_paths
```

**强规则**：
- `db.py` 不 import `schemas.py`，反之亦然（避免循环依赖）
- `services/` 不 import `routers/` 或 `web_app`
- `transcribe_pipeline.py` 不 import `summary_pipeline.py`（独立产物，task_runner 串联）
- `qa_engine.py` 只消费 `TranscriptIndex`，不自己处理 ORM

## 关键设计决策（每条都有具体的"上次踩的坑"做背景）

### 1. 增量逐字稿可见 — ASR 完后立刻写库，不等 diarization

**痛点：** 第一次跑长音频时，ASR 完成后等 pyannote diarization 4 小时，期间 `TaskRow.transcript` 还是 NULL，前端看不到任何 segments。

**修复链：**
- `transcribe_pipeline._record_partial_chunk` 累积 segments + 写 raw.partial.txt
- 通过 `on_partial_transcript` callback → `progress_queue` 扔 `partial_transcript` 消息
- 主进程 `task_runner._apply_partial_transcript` 写库 `transcript={..., partial: True}`
- 前端 `task-detail.js` 检测 `partial=true` 显示绿色 banner "逐字稿已就绪 · 后续阶段还在进行"
- 前端 `task-list.js` 显示 "📄 可读" chip

**测试守卫：** `tests/test_partial_transcript_flow.py`（5 条）

### 2. 三档 speakerMode

`schemas.TaskConfig.speakerMode`：
- `fast` — 不做 diarization，最快
- `llm` — ASR 后 Ollama qwen3:4b 做文本语义角色标注（默认）
- `pyannote` — 声纹 diarization（精确但慢）

旧 `diarize: bool` 字段保留作 backward-compat（`@model_validator` 迁移）。

### 3. 双轨清理

历史上有过：
- `summarizer.py::OllamaSummarizer` + `summary_pipeline.analyze()` 两条摘要路径，靠 `LOCAL_TRANSCRIBER_LEGACY_SUMMARY` env flag 切换
- `chat.py` 里手写的 BM25 + `qa_engine.py` 里 transcript_index BM25 两套检索

**都在 cleanup pass 删干净了。** 现在每件事只有一个实现：
| 功能 | 单一入口 |
|------|---------|
| 摘要 | `summary_pipeline.analyze()` |
| 问答检索 | `qa_engine.QAEngine` + `transcript_index.TranscriptIndex` |
| 配置规范化 | `schemas.normalize_task_config()` |

### 4. 内存自适应

`MemoryBudget.detect()` 决定档位：
- **tight** (`<10GB total or <3GB free`) — Q&A / 摘要锁 qwen3:4b
- **comfortable** — 优先尝试 qwen3:8b
- `model_router.route(TaskKind.X, budget)` 给每个任务（L1/L2/QA）独立选模型

### 5. 滚动窗口分块（VibeVoice 借鉴）

`transcript_chunker.chunk_interview(overlap_chars=N)` — 在分块边界处把前一块尾部追加到下一块 LLM prompt 里（`[上文回顾]\n...\n[本块开始]\n`），缓解发言人轮次切换处的语义割裂。`segment_ids` / `start_time` / `end_time` 不变。

默认 `overlap_chars=0`（保持向后兼容），后续 summary_pipeline 观察 L1 质量后视情况开。

## 反模式（已经踩过、清掉、不要回头做）

| 反模式 | 当时的"理由" | 实际后果 | 治疗方法 |
|--------|-----------|---------|---------|
| 上帝模块（web_app.py 25 routes/867 行）| "都是 FastAPI 装饰器，挤一起没事" | 改一个路由都要 scroll 几百行 | `routers/` + APIRouter |
| 双轨实现 + env flag | "新路径不稳，暂时保留旧路径" | 半年后没人记得 flag 为什么存在，两边都不敢删 | 选一条删另一条；不允许长期共存 |
| 死代码（chat.py 整个文件、_prewarm_digest 线程）| "万一以后用得上" | 新人接手时以为是活路径，浪费时间 | 反向 inspect.getsource 测试守住（见 test_task_runner_no_prewarm.py） |
| Pipeline 名字与内容不符 | "pipeline 是个通用词" | 新人以为它包含摘要 | 改名 `transcribe_pipeline.py` + 类名 `TranscribePipeline` |
| ORM + Pydantic + session 塞一个文件（旧 web_models.py 184 行） | "都是 model 嘛" | 改个 schema 要懂 SQLAlchemy 才能动 | 拆 `db.py` + `schemas.py` |
| 路由处理函数里直接拼 SQL + 调 Ollama | "省得抽 service" | 不可测，没人敢 mock | helper 抽 `services/`，路由只做 IO |

## 测试地图

```
tests/
├── test_partial_transcript_flow.py    ← 增量可见性 5 条回归（item #8）
├── test_task_runner_no_prewarm.py     ← 反向回归，禁止 _prewarm_digest 复活
├── test_qa_engine.py                  ← QAEngine + build_index_for_task
├── test_chat_retrieval.py             已删（被 qa_engine 取代）
├── test_summary_pipeline.py           ← L1/L2 端到端
├── test_hierarchical_summary.py       ← L1/L2 prompt + JSON 解析
├── test_transcript_chunker.py         ← chunk_interview 含 overlap_chars
├── test_transcript_index.py           ← BM25 索引
├── test_task_config.py                ← speakerMode 三档 + diarize 迁移
├── test_speaker_labeler.py            ← LLM 角色标注 + chunk 分批
├── test_pipeline_progress.py          ← progress 映射 + partial 写盘
├── test_web_api.py                    ← FastAPI 端到端集成
├── test_ollama_lifecycle.py           ← OllamaClient
├── test_ollama_match.py               ← check_ollama_model 名字匹配
├── test_model_router.py
├── test_memory_monitor.py
├── test_exporters.py / test_alignment.py / test_hf_paths.py / test_web_app_hf_home.py
└── ...

跑全套：venv/bin/python -m pytest tests/ -q
当前：126 passed
```

## 新 agent 接手 checklist

1. 读这份 `ARCHITECTURE.md`
2. 读 `CLAUDE.md`（项目级硬约束：venv 命名、Python 版本、iCloud 路径等）
3. 读 `README.md`（产品定位 + 硬件要求）
4. 跑一次 `./Check Runtime.command`（验证本机环境）
5. 跑一次 `venv/bin/python -m pytest tests/ -q`（验证代码状态）
6. 找你要改的功能：用上面的"数据流图"+"目录结构"两节定位文件
7. 改之前先 grep "反模式" 表，确认你不在重蹈覆辙

## 持续维护原则

- **每个文件一个清晰职责**。超过 500 行就该考虑拆。当前 `task_runner.py` 655 行是单点风险，下次必要重构时拆 `task_runner/` 子包（runner state machine + worker entry + progress message handler）
- **新功能先写测试再写代码**，TDD 不商量
- **删比加更重要**。死代码不能"先留着"，删干净；要恢复就 git log
- **不引入 backward-compat 长期债务**。临时 flag 写 commit 时就规划清理路径
- **每个 commit 包含 why，不只是 what**（git log 是项目的活文档）
