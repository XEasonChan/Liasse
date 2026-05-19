# 8 小时开发计划：WhisperQwen 桌面 UI

读这份计划前先读 [/CLAUDE.md](../CLAUDE.md) 和 [frontend-spec.md](frontend-spec.md)。本计划是把这两份文档落地为可运行产品的工程方案，所有"待 review"决策已在此锁定。

## 进度

- ✅ **M1 已完成（2026-05-18，pre-flight 跑通）** — 产物：`launch_app.py`、`local_transcriber/web_app.py`、`Start WhisperQwen.command`，pywebview 已装。健康检查全绿，窗口能开。**Agent 从 M2 开始。**

## 已锁定决策（来自 frontend-spec.md D1-D8）

| ID | 决策 |
|---|---|
| D1 | 侧栏只留**「转录」「设置」**。删除原 mockup 的 "总结" / "AI Chat" 单独入口（这两功能都做在详情页内） |
| D2 | 底部状态栏简化为**一行**：「正在处理 xxx.mp3 (45/60 分钟)」+「打开日志」按钮。删除 CPU/RAM/GPU 监控 |
| D3 | 详情页**不带音频播放器**。MVP v1 仅文字编辑 |
| D4 | **不做**时间线 tab。详情页只有两个 tab：「逐字稿」「总结」 |
| D5 | Q&A：第一次提问前，先调 Qwen3:8b 把转录预压缩成结构化要点（人物/事件/观点），缓存到任务对象 `chatContextDigest` 字段，后续 Q&A 都基于这个 digest。digest 大约 1-2k 字，可塞进 8B 的 context |
| D6 | "清空 completed" 改成 **"清空已完成"** |
| D7 | 设置里**加**"完全离线"开关，勾上后 `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` |
| D8 | 删除任务弹窗：「仅从列表移除」/「同时删除转录输出」，原始音频永远不动 |

## 技术架构

```
┌──────────────────────────────────────────────────────────┐
│  桌面进程：launch_app.py                                  │
│  ├─ 启动 FastAPI 在 127.0.0.1:5173 (Uvicorn 子线程)       │
│  └─ pywebview 打开窗口 → http://127.0.0.1:5173          │
└──────────────────────────────────────────────────────────┘
            │
            │ HTTP / SSE
            ▼
┌──────────────────────────────────────────────────────────┐
│  FastAPI 后端 (local_transcriber/web_app.py)             │
│  ├─ /api/tasks               任务列表 / 上传 / 删除       │
│  ├─ /api/tasks/{id}          任务详情                    │
│  ├─ /api/tasks/{id}/edits    用户对逐字稿/发言人名的编辑 │
│  ├─ /api/tasks/{id}/summary  重新生成总结                │
│  ├─ /api/tasks/{id}/chat     Q&A 流（SSE）              │
│  ├─ /api/settings            设置读写                    │
│  ├─ /api/models              模型状态                    │
│  ├─ /api/health              健康检查（ollama 等）       │
│  └─ /                        前端静态文件                │
└──────────────────────────────────────────────────────────┘
            │
            │ 直接 import
            ▼
┌──────────────────────────────────────────────────────────┐
│  现有后端管线（local_transcriber/pipeline.py 等）         │
│  不动它。把 web_app 当作新的入口。                        │
└──────────────────────────────────────────────────────────┘
```

后台跑任务用 **`asyncio.create_task` + `concurrent.futures.ProcessPoolExecutor(max_workers=1)`**：

- 进程池里跑 `LocalTranscriptionPipeline.run()`（CPU/GPU 密集）
- 进度通过 `multiprocessing.Queue` 传回主进程
- 主进程更新 SQLite 任务状态
- 串行执行（一次只跑一个），符合 M1 16GB 内存约束

## 文件清单（待创建）

```
local_transcriber/
├── web_app.py              ← FastAPI 应用，主路由
├── web_models.py           ← Pydantic 请求/响应模型 + SQLAlchemy Task ORM
├── task_runner.py          ← 进程池 + 进度回传
├── chat.py                 ← Q&A 逻辑 + digest 生成 + SSE 流
├── settings_store.py       ← 读写 settings.json
└── web_static/             ← 前端静态文件
    ├── index.html
    ├── app.js              ← Vue 3 应用入口
    ├── style.css           ← 自定义补充 Tailwind
    ├── components/
    │   ├── sidebar.js
    │   ├── upload-zone.js
    │   ├── task-list.js
    │   ├── task-detail.js
    │   ├── chat-panel.js
    │   └── settings-page.js
    └── icons/              ← Inline SVG，从 lucide.dev 选

launch_app.py               ← 项目根，pywebview 入口
Start WhisperQwen.command   ← 双击启动，会启动 ollama 必要时
requirements-mlx.txt        ← 添加 fastapi、uvicorn、pywebview、sqlalchemy、aiosqlite（实际 fastapi 已有，再补 pywebview）
```

## 里程碑

每个里程碑都有：
- **DOD**（done definition）— 写完才能进下一个
- **验证命令** — 能跑就过
- **大致时间** — 用于自评估进度

### M1：脚手架 + 健康检查 — 45 分钟

**做什么**：

1. 装新依赖：`venv/bin/pip install pywebview` 然后 `pip freeze | grep -iE "pywebview|fastapi|uvicorn|sqlalchemy" >> requirements-mlx.txt`（去重）
2. 建 `local_transcriber/web_app.py`，FastAPI 应用，2 个路由：
   - `GET /api/health` → `{ ok: true, checks: { ffmpeg, ollama, hf_cache, models } }`
   - `GET /` → 暂时返回 `"WhisperQwen backend up"` 的 HTML
3. 建 `launch_app.py`：用 uvicorn 在子线程跑 web_app，主线程用 pywebview 开 800x600 窗口
4. 建 `Start WhisperQwen.command`：检查 ollama 在跑 → 启动 `venv/bin/python launch_app.py`

**DOD**：
- 双击 `Start WhisperQwen.command` 后桌面窗口打开，显示 "WhisperQwen backend up"
- `curl http://127.0.0.1:5173/api/health` 返回所有检查为 true

**验证**：
```bash
venv/bin/python -c "import fastapi, uvicorn, pywebview, sqlalchemy; print('imports ok')"
# 然后手动双击 Start WhisperQwen.command 看窗口
curl http://127.0.0.1:5173/api/health
```

### M2：任务持久化 + REST API — 75 分钟

**做什么**：

1. `web_models.py`：SQLAlchemy 模型 `Task`，字段照 frontend-spec.md 第 6 节的 TypeScript 类型 1:1 翻译。Pydantic schema 用于 API。
2. SQLite 库放在 `outputs/tasks.db`。启动时 auto-migrate（`Base.metadata.create_all`）
3. 实现路由：
   - `POST /api/tasks/upload`：multipart 上传一组文件 → 写 SQLite，状态 `queued`。**音频文件不复制**：把用户给的路径存进 `audioPath`
   - `GET /api/tasks?status=...`：列表，支持 `status` 过滤
   - `GET /api/tasks/{id}`：详情，含 segments / edits / chatMessages
   - `DELETE /api/tasks/{id}?delete_outputs=true|false`：实现 D8 决策
   - `POST /api/tasks/{id}/edits/speaker`：改发言人名字
   - `POST /api/tasks/{id}/edits/segment`：改某段文字
4. 写 4-5 个 pytest 单测覆盖 CRUD

**DOD**：
- pytest 全过
- curl 能完成完整生命周期：上传 → 列出 → 看详情 → 改发言人名 → 删除

**验证**：
```bash
pytest tests/test_web_api.py -v
# 然后手动
curl -X POST http://127.0.0.1:5173/api/tasks/upload \
  -F "files=@test_audio/ll7qIcIWWGFSsORHr4yY-UuqAe8h.m4a" \
  -F 'config={"asrModel":"Qwen/Qwen3-ASR-0.6B","diarize":true,"numSpeakers":2,"summarize":false,"language":"Chinese"}'
curl http://127.0.0.1:5173/api/tasks
```

### M3：转录运行器 + 进度回传 — 75 分钟

**做什么**：

1. `task_runner.py`：单 worker `ProcessPoolExecutor(max_workers=1)`
2. 启动一个 background task（FastAPI lifespan）轮询 SQLite，把 `queued` 任务推进 worker
3. Worker 进程调 `LocalTranscriptionPipeline.run(job)`，通过 `multiprocessing.Queue` 回传 `{stage, progress}`
4. 主进程从 queue 读，update SQLite
5. 任务完成后写 `outputs` 路径到 `task.outputs`，状态置 `done`
6. 失败抓异常写 `task.errorMessage`，状态置 `failed`
7. `POST /api/tasks/{id}/stop`：cancel worker，状态置 `stopped`

**DOD**：
- 上传 60 秒测试音频 → 30 秒后 `GET /api/tasks/{id}` 看到 status=done 和 outputs 路径
- 进度字段从 0 涨到 1.0
- 两个任务排队上传，第二个等第一个完成才开始

**验证**：
```bash
# 切个 60 秒样本上传
ffmpeg -y -i test_audio/ll7qIcIWWGFSsORHr4yY-UuqAe8h.m4a -t 60 -ac 1 -ar 16000 /tmp/sample.wav
curl -X POST http://127.0.0.1:5173/api/tasks/upload -F "files=@/tmp/sample.wav" -F 'config={"asrModel":"Qwen/Qwen3-ASR-0.6B","diarize":true,"numSpeakers":2,"summarize":false,"language":"Chinese"}'
# 拿 task id 后轮询
watch -n 2 'curl -s http://127.0.0.1:5173/api/tasks | python3 -m json.tool | head -40'
```

### M4：前端骨架 + 转录主页 — 90 分钟

**做什么**：

1. `web_static/index.html`：Vue 3 + Tailwind CDN，挂载 `#app`
2. `app.js`：Vue 3 app + `createWebHistory` 路由（4 路：`/`、`/task/:id`、`/settings`）
3. `components/sidebar.js`：左侧栏，2 项「转录」「设置」+ 底部模型状态面板（调 `/api/models`）
4. `components/upload-zone.js`：拖拽 + 文件选择 + toggle 行（按 frontend-spec.md 3.3 节）
5. `components/task-list.js`：调 `/api/tasks` 轮询（2s 一次），渲染行，操作按钮按 frontend-spec.md 3.4 节
6. 底部状态栏：一行 + 「打开日志」按钮（点了 alert 或打开 `outputs/run.log` 路径）

**DOD**：
- 主页能拖拽文件、点上传，触发 M3 的任务
- 任务列表实时更新进度（轮询）
- UI 视觉上至少能认出是 frontend-spec.md 描述的设计（不要求像素级 match mockup）

**验证**：手动测试：拖拽 `/tmp/sample.wav` → 点上传 → 看任务列表进度 → 等到 done

### M5：详情页 + Q&A — 90 分钟

**做什么**：

1. `components/task-detail.js`：顶部信息条 + 2 个 tab（逐字稿 / 总结） + 右侧 Q&A 栏
2. **逐字稿 tab**：按发言人分块渲染。每段：可点击改文字（contenteditable）→ blur 时 POST 到 `/api/tasks/{id}/edits/segment`。发言人标签可点击改名 → 全局生效
3. **总结 tab**：渲染 markdown（用 `marked` 或简化版）。「重新生成」按钮 POST `/api/tasks/{id}/summary`
4. `chat.py` 后端：
   - 首次提问前调 ollama 生成 digest（prompt 模板见下）
   - 缓存到 task.chatContextDigest
   - 每次 Q&A：prompt = `system: 这是一段访谈的核心要点 + digest` + 用户消息
   - 通过 SSE 流式返回
5. `components/chat-panel.js`：消息历史 + 输入框 + 发送按钮，用 `EventSource` 接 SSE

**Digest 生成 prompt 模板**：
```
你将看到一段访谈的完整逐字稿。提取以下结构化要点：

1. 访谈基本信息（参与人、估计时长、主题）
2. 关键人物（每个人的角色、立场、知识背景）
3. 主要话题（按出现顺序，每个话题 1-2 句概括）
4. 重要观点与引述（用引号标出关键原话）
5. 待跟进的问题（访谈中提到的悬而未决的点）

逐字稿：
{transcript}
```

Q&A prompt：
```
system: 你是一个研究助理。下面是用户最近转录的一段访谈的核心要点，所有问答都基于此：
{digest}

回答时：
- 如果要点里没有直接答案，明确说"要点中未提及"
- 引用具体观点时附带说话人和大致时间段（如果要点里有）
- 用中文，简洁

user: {question}
```

**DOD**：
- 点已完成任务进详情页
- 改一段文字 → 刷新页面后改动还在
- 重新生成总结能成功调到 ollama
- Q&A 能问"这段访谈讨论了什么？"得到合理回答（基于 digest）
- Q&A 响应是流式（字一个一个出，而不是全部憋住）

**验证**：手动测试整个流程

### M6：设置页 + 离线开关 — 45 分钟

**做什么**：

1. `settings_store.py`：读写 `outputs/settings.json`
2. `GET/PUT /api/settings`
3. 字段：
   ```json
   {
     "outputDir": "~/Documents/WhisperQwen/",
     "fullyOffline": false,
     "defaultASRModel": "Qwen/Qwen3-ASR-0.6B",
     "defaultLanguage": "Chinese",
     "defaultDiarize": true,
     "defaultNumSpeakers": 2,
     "defaultSummarize": true
   }
   ```
4. `components/settings-page.js`：表单 + 模型管理（调 `/api/models` 显示已下载/未下载）
5. 「完全离线」勾上后，后端启动时 `os.environ["HF_HUB_OFFLINE"] = "1"` 和 `os.environ["TRANSFORMERS_OFFLINE"] = "1"`
6. 「一键清空所有任务历史」按钮：DELETE all + 不删 outputs 文件

**DOD**：设置页能看到所有字段、能改、能保存、刷新页面后保留

### M7：打包 + 验收 — 60 分钟

**做什么**：

1. 更新 `README.md`：用户角度的 quickstart（4 步：装 brew 依赖、跑 Setup MLX Test Env、配置 HF token、双击 Start WhisperQwen）
2. ✅ (2026-05-19) 已删除 `run_app.py`（旧入口）和 `Start Local Transcriber.command`；`local_transcriber/app.py`（旧 Tkinter UI）拆出单独清理
3. 验证：在干净 zsh session 里双击 `Start WhisperQwen.command`，完成从 cold-start 到看到任务列表的全流程
4. 写 `outputs/BUILD_REPORT.md`：每个 M1-M7 实际耗时、通过情况、任何遗留 TODO
5. 跑 `pytest tests/ -v` 全过

**DOD**：
- 用户能从双击 `.command` 文件开始，不开终端，完成"上传音频 → 看转录 → 用 Q&A 问问题"全流程
- BUILD_REPORT.md 记完
- 所有测试过

## 工作纪律

1. **严格按 M1→M7 顺序做**，前一个的 DOD 没过不准进下一个
2. 每个 M 开始前重读这一节，明确 DOD
3. 卡住超 30 分钟：在 `outputs/BLOCKED-Mx.md` 写下卡点（含报错截图、试过什么、为什么不行），跳过该 milestone，进下一个能独立做的（M6 设置页和其他大部分独立，可以跳过 M5 先做）
4. 不要重构后端管线 `local_transcriber/{pipeline,asr,diarization,exporters}.py`，它已经工作；新增文件而非修改
5. **不要**为了完美延后：M4 的 UI 视觉上够用就行，不追求像素级 match mockup。「能用 → 好看」的顺序
6. 严禁联网调外部 API（用户 IRB 不允许）。只用本地 ollama + 已下载的 HF 模型
7. 用户在睡觉，**不要中途停下问问题**。所有问题都自己根据 CLAUDE.md + 本文档决定
8. 遇到歧义时：选**简单的、容易测的**那个方案
9. 每个 milestone 完成后 git diff 自检：是不是只动了应该动的文件？有没有意外删了什么？

## 不在范围内（明确不做）

- Electron / Tauri（用 pywebview）
- npm / 任何前端构建步骤（Vue 和 Tailwind 都走 CDN）
- 音频播放器（D3 已锁定不做）
- 时间线 tab（D4 已锁定不做）
- 用户账号 / 协作
- 实时录音转录（只做文件）
- 多语言 UI（只做中文）
- 服务器部署 / 多机
- 测试覆盖率 90%+（pytest 覆盖关键 CRUD 即可，UI 不做自动化测试）
- 性能优化（除非 < 0.3x 实时这种明显异常）

## 完成判据

跑完以下流程，没有崩溃 / 错误，UI 反应合理：

1. 关掉所有终端，**只双击** `Start WhisperQwen.command`
2. 窗口打开，看到主页
3. 拖拽一个 m4a 文件进去
4. 看到任务出现在列表，进度从 0% 涨
5. 等任务完成（60s 样本约 1.5 分钟）
6. 点这一行进详情页
7. 切换"逐字稿"和"总结" tab，内容都正常显示
8. 改一个发言人名字，刷新页面，改动还在
9. 在右侧 Q&A 输入"这段访谈讨论了什么？"，看到字符流式输出，回答合理
10. 进设置页，把"完全离线"勾上，保存。再上传一个文件还能正常处理（模型已经在本地）
