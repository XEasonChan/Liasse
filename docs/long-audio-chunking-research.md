# 长音频切分策略调研报告

> 调研日期：2026-05-19
> 目的：为本地访谈转录工具（Qwen3-ASR + pyannote）设计 3-4 小时音频的分块 / 进度 / 中断恢复机制
> 用户原请求：调研 microsoft/VibeVoice 和 Petal 怎么处理长音频

---

## 项目 1: microsoft/VibeVoice-ASR

**定位**：微软 2026-01 开源的 7B 端到端语音识别模型（Qwen2.5-7B + 7.5Hz acoustic/semantic tokenizer），主打"60 分钟单遍处理、联合输出 Who/When/What"。

**切分策略**：表面宣传"单遍 60 分钟不切分"，实际看 `modeling_vibevoice_asr.py` 的 `_iter_segments` 实现，长音频在 **encoder 层** 是按固定 60 秒等长切（默认 `streaming_segment_duration = 60.0`），但用了 **streaming convolution cache**（`VibeVoiceTokenizerStreamingCache`，类似 KV-cache 思路）让分块之间在因果卷积上保持连续；最后一段加 `is_final_chunk=True` 触发 `extra_padding` 与非流式模式的 `ceil` 对齐保持一致。切完之后把所有段的 acoustic / semantic mean 在时间维上 `torch.cat` 起来，**整体丢进一次 LLM `generate()` 调用**。`audio_duration < 60s` 时直接走非流式分支。

**进度暴露 / checkpoint**：模型本身**没有**段级 checkpoint，也没有恢复机制。Gradio demo 用 HuggingFace `TextIteratorStreamer`，**按 LLM 生成的 token 流式 yield**，前端能看到 "🔴 LIVE Streaming Output (tokens: N, time: Xs)" 实时滚动。一旦中断就整段从头来过。

**输出合并**：encoder 段不重叠，靠卷积 cache 保证边界连续；LLM 单次生成所以没合并问题。Speaker ID + 时间戳是端到端模型直接产物（结构化 `[start_time - end_time] Speaker N: text`），由 `post_process_transcription` regex 解析。

**关键限制**：**64K context 上限 ≈ 60 分钟硬天花板**；3-4 小时音频它根本喂不下去，必须用户在外面切。仓库没提供任何外部切片 + 拼接的脚本。

---

## 项目 2: Petals → 实为 m-bain/whisperX

GitHub `bigscience-workshop/petals` 是分布式 LLM 推理框架（BitTorrent 风格跑 Llama 405B / Mixtral），**与音频无关**。"petal audio chunking" 也找不到对应项目。改用 audio 域里同样做"长音频 + VAD 切分 + diarization + 时间戳"的公认参考实现 **WhisperX**（ETH/Oxford，INTERSPEECH 2023，Ego4D 转录冠军）。

**切分策略**：**VAD-driven cut & merge**。先跑 VAD（默认 pyannote，可选 silero），得到所有语音活动段；再 `merge_chunks(segments, chunk_size=30, onset=0.500, offset=0.363)` 贪心合并相邻段，**当累计跨度 > 30 秒就开一个新 chunk**——也就是说每个 chunk 是"≤30 秒的语音活动并集"，而**不是等长 30 秒**，静音被裁掉。这就是 WhisperX 论文宣称的"减少幻觉、支持 batched inference 且 WER 不退化"的核心。

**独立处理 vs sliding window**：每个 VAD chunk **完全独立**喂给 faster-whisper，可 batch 化并行。不做 sliding window — VAD 边界本身就是语义自然停顿，所以没重叠区。

**跨段说话人 / 时间戳**：分三阶段：
1. ASR 出文本 + 段级时间戳
2. 单独跑 pyannote diarization **on the full audio**（不在 chunk 内），得到全局 speaker turns
3. 用 wav2vec2 forced alignment 拿 word-level timestamps，再把 speaker turns assign 到 word 上

这样跨 chunk 的 speaker ID 是**全局一致**的。

**进度暴露 / checkpoint**：`transcribe.py` 有 `progress_callback` 钩子和 `print_progress` 选项，**按 VAD chunk 报百分比**（`((idx+1) / total_segments) * 100`）。没有磁盘 checkpoint，但因为每段独立纯函数，外面套一层"已完成段缓存到 SQLite"就能实现 resume。

**输出合并**：直接 append `{"text", "start", "end", "avg_logprob"}` 列表，无 dedup（VAD 切的 chunk 天然不重叠）。

---

## 给本地访谈转录工具的 5 条具体借鉴

### 1. 不要相信"单遍 N 小时"宣传，必须显式切

VibeVoice 7B 标称 60 分钟单遍，实际 encoder 也是 60s 切片 + cache 拼接；它的 64K context 决定了 3-4 小时音频任何上游模型都得在 **mlx-qwen3-asr 之外** 显式切。我们应当在 `local_transcriber/pipeline.py` 增加一层 **pre-chunker**，不要赌 `mlx-qwen3-asr` 内部 30s window 能优雅吃完 3.5 小时。

### 2. 采用 WhisperX 的 "VAD cut + 上限阈值 merge" 策略

不要用等长切。具体参数照抄：

- silero VAD（已经在 pyannote 4.x 体系里）
- `max_chunk = 30s`
- `vad_onset = 0.5` / `vad_offset = 0.363`
- silero 的 `max_speech_duration_s` 参数保证最长段不爆 ASR window，同时静音切点 = 语义切点，减少跨段词被切断

### 3. chunk 级独立处理 + SQLite checkpoint 实现 resume

每段 ASR 完成立刻写一行 `(task_id, chunk_idx, start_s, end_s, text, speaker_assign_pending)` 到 `outputs/tasks.db`；启动时先 query "这个 task 已完成到哪个 chunk_idx"，从下一段继续。

这正是 WhisperX 没做但**它的纯函数结构使其极易加上**的特性——我们直接做。

### 4. 说话人识别放在 chunk 之外、全局做一次

VibeVoice 是端到端联合预测（chunk 内做不到全局一致），WhisperX 是 ASR 切 chunk + diarization 跑整段 + 后置 assign——**WhisperX 这个分离架构对 resume 友好得多**。

我们 pyannote diarization 应该跑在原始整段音频上（一次性，无 chunk），然后 ASR 段的 `(start, end)` 去查 speaker turn 表做对齐。`local_transcriber/alignment.py` 已经做了类似事情，确认是这个方向即可。

### 5. 进度暴露用两层并行

- **粗粒度**：按 chunk 报（`完成 N/M chunks, ETA = 剩余 chunks × 平均 chunk 耗时`），给前端进度条用
- **细粒度**：参考 VibeVoice Gradio demo 的 `TextIteratorStreamer` 模式——单 chunk 内 ASR 出文本时 SSE 把 partial text 推给前端，让用户看到"正在转录的当前句"

两层结合既能精确算 ETA（粗粒度）又有"活着"的视觉反馈（细粒度），比 mlx-qwen3-asr 当前完全黑盒强很多。

---

## 实施建议（按优先级）

### P0：3-4 小时音频可恢复 + 真实进度（建议本周做）

```
local_transcriber/chunker.py（新建）
  ├─ pre_chunk_audio(audio_path) → list[Chunk]    # silero VAD + 30s merge
  ├─ Chunk: { start_s, end_s, idx, total }
  └─ ffmpeg slicing or direct sample-range read

local_transcriber/pipeline.py（重构）
  ├─ 拿到 chunks → 跑 diarize_full_audio()（整段，一次）
  ├─ for chunk in chunks:
  │     query SQLite: 这个 chunk 是否已完成？
  │     若否: transcribe_chunk() → 写 SQLite chunk_results 表
  │     回调 progress = idx / total
  ├─ alignment：把每个 chunk_result + global_diarization 对齐
  └─ 合并所有 chunk 文本 → markdown/json/srt

local_transcriber/web_models.py
  └─ 新表 ChunkResult(task_id, chunk_idx, start_s, end_s, text, segments_json, completed_at)

UI：详情页已完成段实时显示（轮询 chunks API）
```

预计：1-1.5 天工程。

### P1：streaming partial text（增强体验，可选）

mlx-qwen3-asr 不暴露内部进度，要做这层需要自己实现 sliding window over chunk（每 2-3 秒 reflush 一次 partial transcription），跟 P0 串联。可选，影响 UX 不影响功能。

### P2：跨进程并行 chunks（深度优化）

当前 task_runner 串行处理任务，但 chunk 之间可以并行（多个 mlx 子进程同时跑不同 chunk）。16GB 内存 + MLX 共享 GPU 上限制并发数 = 1-2。M4 Pro 24GB 可以 2-3。

会让 3.5 小时音频从 3 小时降到 1.5 小时。但增加内存压力，需要测试。

---

## 相关源码位置（已 clone 到 /tmp/）

- `/tmp/VibeVoice/vibevoice/modular/modeling_vibevoice_asr.py:213-330` — 60s 段切分 + streaming cache
- `/tmp/VibeVoice/vibevoice/processor/vibevoice_asr_processor.py:333` — `<60s` 自动关闭流式
- `/tmp/VibeVoice/demo/vibevoice_asr_gradio_demo.py:614-655` — TextIteratorStreamer 用法
- `/tmp/whisperX/whisperx/vads/vad.py:20-53` — merge_chunks 贪心算法
- `/tmp/whisperX/whisperx/vads/silero.py:22-46` — silero 参数
- `/tmp/whisperX/whisperx/asr.py:197-298` — VAD-driven transcribe + progress_callback

---

## 参考链接

- [WhisperX GitHub](https://github.com/m-bain/whisperx) — 长音频 ASR 标杆
- [WhisperX 论文](https://arxiv.org/pdf/2303.00747)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — WhisperX 底层 backbone
- [VibeVoice GitHub](https://github.com/microsoft/VibeVoice) — 微软 7B 端到端模型
- [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) — 我们用的模型
