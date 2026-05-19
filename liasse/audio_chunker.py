"""VAD-aware 音频切分。

借鉴 OpenWhispr 的 Whisper-VAD 配置参数(reference/openwhispr-main/src/
constants/whisperVad.json):
  threshold:        0.5    # Silero VAD 阈值
  minSpeechMs:      250    # 短于此的「语音」丢弃(过滤噪声)
  minSilenceMs:     200    # 段内允许的最长静默
  maxSpeechS:       30     # 段最长上限,超过强切
  speechPadMs:      100    # 段前后各留 padding

为什么要 VAD pre-chunk:
- 当前 mlx-qwen3-asr 按内部 30s 静默切分,但访谈里很多发言之间没有长静默,
  ASR 给出 60-90s 长 segment,一段跨越多个 speaker turn → alignment 把
  整段归一人
- VAD 主动切到 ≤ 30s,且切点落在静默处,**自然避免跨 speaker**

接口:vad_chunk(audio_path) → List[{"start": float, "end": float}]
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List


def vad_chunk(
    audio_path: Path | str,
    threshold: float = 0.5,
    min_speech_duration_ms: int = 250,
    min_silence_duration_ms: int = 200,
    max_speech_duration_s: float = 30.0,
    speech_pad_ms: int = 100,
) -> List[Dict[str, float]]:
    """返回 chunk 时间窗口列表 [{"start": float, "end": float}, ...]。

    时间单位:秒。失败抛 RuntimeError(调用方决定 fallback 单 chunk 老路径)。
    """
    try:
        from silero_vad import (
            load_silero_vad,
            read_audio,
            get_speech_timestamps,
        )
    except ImportError as exc:
        raise RuntimeError(
            "silero-vad 未安装。pip install silero-vad"
        ) from exc

    audio_path = Path(audio_path)
    model = load_silero_vad()
    wav = read_audio(str(audio_path))  # 自动 16k mono float32 tensor

    raw = get_speech_timestamps(
        wav,
        model,
        threshold=threshold,
        min_speech_duration_ms=min_speech_duration_ms,
        min_silence_duration_ms=min_silence_duration_ms,
        max_speech_duration_s=max_speech_duration_s,
        speech_pad_ms=speech_pad_ms,
        return_seconds=True,
    )
    return [
        {"start": float(t["start"]), "end": float(t["end"])} for t in raw
    ]
