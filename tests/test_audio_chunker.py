"""VAD chunker 契约测试。用合成 sine wave 音频,不依赖外部样本。"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def _synth_audio(tmp_path: Path, segments_sec: list, sample_rate: int = 16000) -> Path:
    """生成 wav:指定时段有 440Hz sine,其余静音。"""
    total_sec = max(end for _, end in segments_sec) + 1.0
    n_samples = int(total_sec * sample_rate)
    samples = np.zeros(n_samples, dtype=np.float32)
    for start, end in segments_sec:
        s = int(start * sample_rate)
        e = int(end * sample_rate)
        t = np.arange(e - s) / sample_rate
        samples[s:e] = 0.6 * np.sin(2 * np.pi * 440 * t)
    p = tmp_path / "synth.wav"
    with wave.open(str(p), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes((samples * 32767).astype(np.int16).tobytes())
    return p


def test_chunker_returns_list_for_synth_audio(tmp_path):
    """合成 sine wave 不一定被 Silero 识别为 speech(它训练的是人声),
    但函数不能抛错。"""
    from liasse.audio_chunker import vad_chunk
    audio = _synth_audio(tmp_path, [(0.5, 5.5)])
    chunks = vad_chunk(audio)
    assert isinstance(chunks, list)
    for c in chunks:
        assert "start" in c and "end" in c
        assert c["end"] > c["start"]


def test_chunker_respects_max_duration(tmp_path):
    """maxSpeechDurationS=2 → 每个 chunk 不超过 2.5s(含 pad)。"""
    from liasse.audio_chunker import vad_chunk
    audio = _synth_audio(tmp_path, [(0.0, 20.0)])
    chunks = vad_chunk(audio, max_speech_duration_s=2.0, speech_pad_ms=100)
    for c in chunks:
        assert (c["end"] - c["start"]) <= 2.5, f"chunk {c} 超过 max+pad"


def test_chunker_real_audio_if_available(tmp_path):
    """在真实样本上跑(如果存在),验证 chunk 时间窗合理。"""
    sample = (Path(__file__).resolve().parent.parent
              / "scripts" / "benchmark" / "samples" / "s1-opening.m4a")
    if not sample.exists():
        return
    from liasse.audio_chunker import vad_chunk
    chunks = vad_chunk(sample, max_speech_duration_s=30.0)
    assert len(chunks) > 1, "5 分钟样本应至少切 1 段以上"
    for c in chunks:
        dur = c["end"] - c["start"]
        assert 0.1 < dur <= 30.5, f"chunk dur {dur} 不合理"
    total = sum(c["end"] - c["start"] for c in chunks)
    assert total < 320, f"total speech {total} 超过音频长"
