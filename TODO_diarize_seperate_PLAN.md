# 三档发言人处理方案

## Summary

把当前单一 `diarize: true/false` 改成三档 `speakerMode`，默认使用 **智能档**：

- `fast` / 快速转录：只跑 Qwen3-ASR + 时间戳，不做发言人分离，最快出全文。
- `llm` / 智能分离：先跑 Qwen3-ASR，不跑 pyannote；再用本地 Ollama `qwen3:4b` 根据文本语义把片段标成采访者/受访者等角色。默认档。
- `pyannote` / 精确声纹：保留现有 pyannote 声纹 diarization，作为用户明确选择的慢速精确模式。

本阶段不接入 VibeVoice / Sortformer，不删除 pyannote，只把 pyannote 从默认主路径移出。

## Key Changes

- 配置接口新增：
  ```ts
  speakerMode: "fast" | "llm" | "pyannote"
  defaultSpeakerMode: "fast" | "llm" | "pyannote"
  ```
  旧字段 `diarize` 暂时保留兼容：旧任务 `diarize:true` 按 `pyannote` 运行，旧设置 `defaultDiarize:true` 迁移为新默认 `llm`。

- 前端上传区把“发言人识别”按钮改成三段控制：
  `快速转录 / 智能分离 / 精确声纹`。
  `llm` 需要 Ollama + `qwen3:4b`；`pyannote` 需要 pyannote 模型；缺模型时沿用现有 model-required modal。

- 任务列表参数显示改为模式优先：
  `智能分离 · 2人 · 0.6B 快速 · 中文`，不再只显示“2人/无发言人”。

- 设置页新增“默认发言人处理”三段控制，默认值为 `llm`；保留人数默认值，智能档和精确档都使用它，快速档忽略人数。

- 后端 `TaskConfig` 增加 `speakerMode`，并提供统一 normalization：
  `fast` -> `diarization_enabled=False`；
  `llm` -> `diarization_enabled=False` + 后置 LLM 标注；
  `pyannote` -> `diarization_enabled=True` + 现有 MPS 加速和 progress hook。

- 新增本地模块 `speaker_labeler.py`：
  输入 ASR segments，按最多 80 段或 12000 字分块调用 Ollama，要求返回严格 JSON：`[{id, speaker}]`。
  输出稳定 speaker id：`SPEAKER_00`, `SPEAKER_01`；默认 2 人，用户指定 3/4/5 时扩展允许集合。
  同时给 `edits.speakerLabels` 写入建议名，如 `SPEAKER_00 -> 采访者`、`SPEAKER_01 -> 受访者`，但不覆盖用户已有改名。

- 运行流程：
  `fast`: ASR 结束即导出。
  `llm`: ASR 完成后进度显示“正在智能区分发言人”，失败则保留快速逐字稿并把 `transcript.warnings` 写为“智能分离失败，已保留未分离逐字稿”。
  `pyannote`: 沿用现有 pyannote 进度和导出逻辑。

## Public/API Shape

- Task `config` 示例：
  ```json
  {
    "asrModel": "Qwen/Qwen3-ASR-0.6B",
    "language": "Chinese",
    "speakerMode": "llm",
    "numSpeakers": 2,
    "autoSegment": true,
    "summarize": false,
    "enableChat": true,
    "summaryModel": "qwen3:4b"
  }
  ```

- Task `transcript` 可新增只读元信息：
  ```json
  {
    "segments": [],
    "partial": false,
    "speakerModeEffective": "llm",
    "warnings": []
  }
  ```

- `/api/settings` 增加 `defaultSpeakerMode`；读取旧 `defaultDiarize` 时做兼容，写回时保存新字段。

## Test Plan

- 单元测试：`TaskConfig` normalization 覆盖新三档、旧 `diarize:true/false`、缺失字段。
- 单元测试：`speaker_labeler` 解析合法 JSON、处理 malformed JSON、处理 Ollama 不可用 fallback。
- 后端测试：创建任务时三种 `speakerMode` 都能持久化；旧 config 不报错。
- Worker 测试：mock pipeline，断言 `fast/llm` 不传 `diarization_enabled=True`，`pyannote` 才触发 pyannote 加速/hook。
- 手动验证：60 秒样本分别跑三档；智能档应比 pyannote 快并产出至少两个角色标签；精确档仍显示 pyannote 阶段进度。
- 回归测试：`pytest tests/`、`./Check Runtime.command`。

## Assumptions

- 默认档位按用户确认设为 `llm` 智能分离。
- 智能档是“文本语义角色标注”，不是声纹识别；UI 文案必须避免暗示它能听出真实音色。
- 本阶段所有 LLM 调用只走本地 Ollama，不新增任何云 API。
- 现有已创建任务的 config 不自动改写；重试旧任务时按旧任务原 config 运行。
