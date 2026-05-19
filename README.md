<p align="center">
  <img src="docs/assets/liasse-hero.png" alt="Liasse — private local transcription for interviews and case files" width="100%">
</p>

<h1 align="center"><em>Liasse</em></h1>

<p align="center">
  <em>Private local transcription for interviews and case files.</em><br>
  <sub>本地访谈转录 · 不上传云端 · 不调用第三方 API</sub>
</p>

<p align="center">
  <a href="#中文">中文</a> · <a href="#english">English</a> · <a href="#use-cases">Use cases</a> · <a href="#customize-with-codex">Customize</a>
</p>

---

## 中文

> Liasse（法语：一束被妥善收束起来的档案材料）是一个把访谈录音变成可引用、可归档、不离开本机的逐字稿的桌面应用。  
> 它的目标用户不是开发者，而是研究者、律师、合规官、口述史学者、田野调查者——任何手里有"不能上传"的录音的人。

Liasse 不打算成为又一个"AI 录音工具"。它的形态参考的是研究者桌上那一束被丝带束起来的访谈材料：所有原件都在你这里，工具只是帮你把它们整理得更整齐。音频、逐字稿、总结、问答上下文，从下载模型那一刻起到导出 PDF，都不离开这台机器。

它在 **Apple Silicon Mac 上完全本地运行**——常见的 8GB MacBook Air 就够（速度慢一些但跑得通），16GB 是日常档，24GB+ 可上 1.7B ASR + Qwen3-8B 总结。**完全离线**开关一打开，连首次下载模型之外的所有网络调用都被禁用。

> 当前状态：alpha · 后端管线打通，桌面 UI 可用。如果你是机构采购或合规官，先翻到 [Privacy 一节](#隐私模型)。

<a id="use-cases"></a>

## Use cases · 六个真实场景

Liasse 的命名和形态来自 2026 年 5 月的一次多角色品牌沙盘——六个目标用户在同一个产品环境里给出了反馈与画像（[完整调研](outputs/brand_consulting_report.html)）。下面是被那次调研抽出来的六种使用方式。

<table>
<tr>
<td width="50%" valign="top">
<img src="docs/assets/use-case-1-academic.png" alt="Sensitive Interviews for EU academic researchers"><br>
<strong>Sensitive Interviews · 学术访谈</strong><br>
<sub>For academic researchers</sub><br><br>
GDPR-clean, IRB-bound, never uploaded. 可直接写进 Data Management Plan，伦理审查材料引用 Liasse 作为本地处理工具。
</td>
<td width="50%" valign="top">
<img src="docs/assets/use-case-2-compliance.png" alt="Compliance and audit for DPO / IRB officers"><br>
<strong>Compliance &amp; Audit · 合规与审计</strong><br>
<sub>For DPO &amp; IRB officers</sub><br><br>
DMP-ready · audit-friendly · no cloud anywhere. 输出 audit bundle，包含转录、说话人、保留期限和完整本地处理日志。
</td>
</tr>
<tr>
<td width="50%" valign="top">
<img src="docs/assets/use-case-3-litigation.png" alt="Deposition prep for US litigators"><br>
<strong>Deposition Prep · 庭前准备</strong><br>
<sub>For litigators</sub><br><br>
Privileged · confidential · on your machine. 笔录可作脚注引用，不进任何 vendor log。Privilege 不外泄。
</td>
<td width="50%" valign="top">
<img src="docs/assets/use-case-4-paralegal.png" alt="Case management at scale for paralegals"><br>
<strong>Case Management at Scale · 批量案件</strong><br>
<sub>For paralegals &amp; legal ops</sub><br><br>
Hundreds of hours, batched and bound. 按 matter number 编排队列，导出 Markdown / SRT / JSON，本地全程。
</td>
</tr>
<tr>
<td width="50%" valign="top">
<img src="docs/assets/use-case-5-oralhistory.png" alt="Oral history for humanities researchers"><br>
<strong>Oral History · 口述史</strong><br>
<sub>For oral historians</sub><br><br>
Voices preserved · pages bound. 长达 3-4 小时的访谈，多说话人精确标签，可作专著方法论章节引用。
</td>
<td width="50%" valign="top">
<img src="docs/assets/use-case-6-field.png" alt="Bilingual field research"><br>
<strong>Field Research, Bilingual · 田野研究</strong><br>
<sub>For field researchers</sub><br><br>
Bilingüe · both private. 中 / 英 / 西多语言转录与本地保留，离线机器在田野也可用。
</td>
</tr>
</table>

> 这些不是 hypothetical 用例——它们对应六个具体的画像（欧洲社科 PI、大学 DPO / IRB、美国诉讼律师、paralegal、口述史研究者、西语 / 拉美研究项目负责人）。每个画像在调研里都被独立打分，每一项都让 Liasse 排第一。

## 这不是一个"开发者工具"

Liasse 是一个**有 taste 的本地 LLM 产品**——目标是让任何人都能装、能用、能信任。但它也不是一个封闭的黑盒：

- **默认即用** — 双击 `Start Liasse.command`，跑完安装就能转录。不需要懂 Python、不需要懂 ML。
- **可读可改** — 整个产品是 Python + Vue 3 CDN，没有 webpack、没有 npm 构建、没有 React 框架。任何懂一点点代码的人，加上一个 AI agent（Codex / Claude Code / Cursor），就能在半小时里把界面、文案、模型选型改成自己的样子。详见下面 [Customize with Codex](#customize-with-codex)。
- **零云依赖** — 一旦模型在本地，App 永远不联网。设置里的"完全离线"开关把 `HF_HUB_OFFLINE=1` 和 `TRANSFORMERS_OFFLINE=1` 都强制开启。

<a id="customize-with-codex"></a>

## Customize with Codex

Liasse 故意保持小、可读、无构建步骤——这样**任何 AI coding agent 都能在你的机器上理解并修改它**：

```bash
# 用 Claude Code（推荐）
cd "Liasse 项目目录"
claude

# 或者 Codex CLI
codex
```

然后用自然语言提需求即可：

- "把侧边栏的 Liasse 字标换成我们实验室的名字。"
- "新增一个『去隐私信息』功能，自动把转录里的人名替换为 [P1] [P2]。"
- "把总结模板改成 IRB 报告格式。"
- "西语场景里默认使用 1.7B ASR，其他语言用 0.6B。"

代码组织（`liasse/` Python 包 + `web_static/` Vue 3 前端）和设计系统（[`design.md`](design.md) 是 single source of truth）都为这种"AI 协作改造"做了准备。

## 隐私模型

Liasse 的隐私边界是「你的本机」：

- 音频文件不会上传到任何云转录 API。
- 逐字稿、总结、digest、问答历史保存在本地 `outputs/` 和 SQLite。
- 首次下载模型需要联网；下载完后开启「完全离线」模式即可永久断网运行。
- 不做 telemetry，不检查更新，不把任何材料发送给第三方服务。
- 模型推理全部在本机 Apple Silicon GPU（MLX / Metal）上完成。
- 错误日志和崩溃报告也只写到 `~/Library/Logs/Liasse/`，不上传。

## How it works

<p align="center">
  <img src="docs/assets/liasse-workflow.png" alt="Liasse local workflow: drop audio → ASR → speaker labeling → summary → export" width="100%">
</p>

五步，都在本机：

1. **拖入音频** — `mp3 / wav / m4a / flac / aac / ogg / wma / mp4`
2. **Qwen3-ASR 转录** — 默认 0.6B，质量模式可切 1.7B（Apple Silicon Metal GPU）
3. **说话人标记** — pyannote 4.x community-1，或更轻的 LLM 文本标记
4. **总结与 Q&A** — Ollama 本地 Qwen3:4b 或 8b
5. **导出 bundle** — Markdown / JSON / SRT；law-firm 场景可走 PDF 打印模板

## 已有能力

| 模块 | 当前实现 |
|---|---|
| 桌面壳 | pywebview + 本地 FastAPI + Vue 3（无 npm 构建） |
| ASR | Qwen3-ASR-0.6B 默认，Qwen3-ASR-1.7B 可选 |
| 说话人识别 | pyannote 4.x `speaker-diarization-community-1` 或 LLM 文本标记 |
| 任务系统 | SQLite 持久化，队列串行执行，失败/中断可重试 |
| 多语言 UI | 中 · 英 · 西 |
| 总结 | Ollama 本地 Qwen3 生成 Markdown 总结 |
| Q&A / RAG | digest + 检索上下文 |
| 导出 | Markdown / JSON / SRT，PDF 走 `@media print` 模板 |
| 离线 | "完全离线"开关，强制 HF / Transformers 走本地缓存 |

## 硬件与内存

| 配置 | 说明 |
|---|---|
| **推荐最低** | Apple Silicon Mac，**8GB 统一内存**（常见于 MacBook Air）。可完成转录 + 4B 总结 / 问答；长访谈耗时会明显变长。 |
| **推荐日常** | **16GB**（MacBook Air / Pro、入门 iMac）。开发与实测主要在这一档。 |
| **更宽裕** | 24GB+。可安装 `qwen3:8b`、选用 1.7B ASR，质量更高。 |

不需要独立显卡或台式工作站。**不建议** Intel Mac、8GB 以下、或同时开很多浏览器标签 / 虚拟机的环境。

## 快速开始

```bash
# 1. 系统依赖
brew install python@3.12 ffmpeg ollama

# 2. Hugging Face token（用于首次下载 pyannote 模型）
echo "HF_TOKEN=hf_xxx" >> .env
echo "PYANNOTE_AUTH_TOKEN=hf_xxx" >> .env

# 3. Python 环境
./Setup\ MLX\ Test\ Env.command

# 4. 本地总结 / 问答模型（8GB 机器只装 4B）
ollama pull qwen3:4b
# 可选：16GB+ 可加 8B
ollama pull qwen3:8b

# 5. 跑起来
ollama serve            # 单独终端
./Start\ Liasse.command  # 双击或命令行
```

`Start Liasse.command` 只检查 Ollama 在跑，不主动启动守护进程。

## 速度参考

Qwen3-ASR-0.6B + 说话人识别（约 0.6–0.7× 实时）：

| 音频长度 | 16GB | 8GB |
|---|---|---|
| 60 秒 | ~90 秒 | ~1.5–2.5 分钟 |
| 5 分钟 | ~7–8 分钟 | ~10–15 分钟 |
| 30 分钟 | ~45 分钟 | ~1–1.5 小时 |
| 3 小时 50 分钟 | ~5–6 小时 | 建议过夜或分段 |

长音频目前是「整段重试」，未来计划切成 10-30 分钟段做局部 resume。

## 项目结构

代码组织参见 [ARCHITECTURE.md](ARCHITECTURE.md)；设计系统参见 [design.md](design.md)。

## Roadmap

- 长音频 chunking + 局部恢复
- 按时间段 / 说话人 / 主题的本地语义检索
- macOS App Bundle / DMG / 首次启动向导
- 暗色模式（v0.3）
- PDF 导出模板的法律 / 学术两种 preset

## 许可

暂未选择开源许可证。请先不要把它当作可自由再分发的软件使用。

---

<a id="english"></a>

## English

> Liasse (French: *a bound bundle of documents tied with a ribbon*) turns interview recordings into citable, archivable transcripts that never leave your machine.  
> It is not for developers. It is for researchers, lawyers, compliance officers, oral historians, and field workers — anyone whose recordings cannot be uploaded.

Liasse is not another "AI recorder." Its shape is borrowed from the bundle of interview materials on a researcher's desk: the originals stay with you; the tool only helps you keep them tidy. Audio, transcripts, summaries, Q&A context — from the moment models are downloaded to the moment you export a PDF — never leave this machine.

It runs **fully locally on Apple Silicon Mac**. An ordinary **8GB MacBook Air is enough** (slower, but it works); 16GB is the daily driver; 24GB+ lets you use the 1.7B ASR and the 8B summarizer. With **fully-offline mode** on, no network calls happen at all after the first model download.

> Status: alpha · backend pipeline working, desktop UI usable. If you are an institutional buyer or a compliance officer, start with the [Privacy](#privacy-model) section.

### Use Cases · six real scenarios

The shape and name of Liasse came from a 2026-05 multi-persona brand sandbox — six target users gave structured feedback in the same product environment ([full research](outputs/brand_consulting_report.html)). The six use cases below are the patterns that emerged.

<table>
<tr>
<td width="50%" valign="top">
<img src="docs/assets/use-case-1-academic.png" alt="Sensitive Interviews"><br>
<strong>Sensitive Interviews</strong><br>
<sub>For academic researchers</sub><br><br>
GDPR-clean, IRB-bound, never uploaded. Can be written directly into the Data Management Plan.
</td>
<td width="50%" valign="top">
<img src="docs/assets/use-case-2-compliance.png" alt="Compliance &amp; Audit"><br>
<strong>Compliance &amp; Audit</strong><br>
<sub>For DPO &amp; IRB</sub><br><br>
DMP-ready · audit-friendly · no cloud anywhere. Export an audit bundle with retention, processors, full local log.
</td>
</tr>
<tr>
<td width="50%" valign="top">
<img src="docs/assets/use-case-3-litigation.png" alt="Deposition Prep"><br>
<strong>Deposition Prep</strong><br>
<sub>For litigators</sub><br><br>
Privileged · confidential · on your machine. Transcripts citable in court filings without entering any vendor log.
</td>
<td width="50%" valign="top">
<img src="docs/assets/use-case-4-paralegal.png" alt="Case Management at Scale"><br>
<strong>Case Management at Scale</strong><br>
<sub>For paralegals &amp; legal ops</sub><br><br>
Hundreds of hours, batched and bound. Queue by matter number, export Markdown / SRT / JSON, all local.
</td>
</tr>
<tr>
<td width="50%" valign="top">
<img src="docs/assets/use-case-5-oralhistory.png" alt="Oral History"><br>
<strong>Oral History</strong><br>
<sub>For oral historians</sub><br><br>
Voices preserved · pages bound. Long-form, speaker-labeled, citable for a monograph's methodology chapter.
</td>
<td width="50%" valign="top">
<img src="docs/assets/use-case-6-field.png" alt="Field Research, Bilingual"><br>
<strong>Field Research, Bilingual</strong><br>
<sub>For field researchers</sub><br><br>
Bilingüe · both private. EN / ES / ZH transcription kept locally — works offline in the field.
</td>
</tr>
</table>

### This is not "a developer tool"

Liasse is **a tasteful local-LLM product**, designed so anyone can install, use, and trust it. But it is not a black box either:

- **Default-just-works** — Double-click `Start Liasse.command`, finish the setup, transcribe. No Python, no ML knowledge required.
- **Readable and modifiable** — The whole product is Python + Vue 3 from CDN. No webpack, no npm build, no React framework. Anyone with a little code experience, plus an AI agent (Codex / Claude Code / Cursor), can reshape the UI, copy, or model choices in under an hour. See [Customize with Codex](#customize-with-codex) above.
- **Zero cloud dependence** — Once models are local, the app never goes online. A "fully offline" toggle in settings forces `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`.

<a id="privacy-model"></a>

### Privacy Model

Liasse's privacy boundary is "your machine":

- Audio is never uploaded to a cloud transcription API.
- Transcripts, summaries, digests, and Q&A history stay in local `outputs/` and SQLite.
- The only network call is the first model download. After that, toggle "Fully offline" — done.
- No telemetry, no update checks, no third-party reporting.
- Inference runs on local Apple Silicon GPU (MLX / Metal).
- Crash logs go only to `~/Library/Logs/Liasse/` and are not sent anywhere.

### Quickstart

```bash
brew install python@3.12 ffmpeg ollama

echo "HF_TOKEN=hf_xxx" >> .env
echo "PYANNOTE_AUTH_TOKEN=hf_xxx" >> .env

./Setup\ MLX\ Test\ Env.command

ollama pull qwen3:4b              # for 8GB machines
ollama pull qwen3:8b              # optional, 16GB+

ollama serve                       # separate terminal
./Start\ Liasse.command            # double-click launcher
```

### Speed Reference

Qwen3-ASR-0.6B + diarization (about 0.6–0.7× realtime):

| Audio length | 16GB | 8GB |
|---|---|---|
| 60 s | ~90 s | ~1.5–2.5 min |
| 5 min | ~7–8 min | ~10–15 min |
| 30 min | ~45 min | ~1–1.5 h |
| 3 h 50 min | ~5–6 h | overnight / split |

Long audio currently retries from the start. Chunked resume is on the roadmap.

### Project Structure

See [ARCHITECTURE.md](ARCHITECTURE.md); design system in [design.md](design.md).

### License

No open-source license selected yet. Please do not treat it as freely redistributable.

---

<p align="center">
  <sub><em>Liasse</em> · A research instrument that happens to be software.</sub>
</p>
