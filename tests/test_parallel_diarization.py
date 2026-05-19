"""验证 pyannote 与 ASR 并行执行。

旧路径：mlx_qwen3_asr.transcribe(diarize=True) 内部串联，3h 音频
要等 ASR 完才开始 pyannote，pyannote 又 10-15 分钟，总时间累加。

新路径：TranscribePipeline._run_parallel_asr_and_diarization
开一个 thread 跑 PyannoteDiarizer，主线程跑纯 ASR；总时间 ≈
max(ASR, pyannote) 而不是 ASR + pyannote。

这套测试不实跑模型 — 全部用 mock 模拟 ASR / pyannote 各自的耗时。
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from liasse.models import (
    PipelineResult,
    SpeakerTurn,
    TranscriptionJob,
    TranscriptSegment,
)
from liasse.transcribe_pipeline import TranscribePipeline


@pytest.fixture
def fake_job(tmp_path):
    audio = tmp_path / "in.m4a"
    audio.write_bytes(b"fake")
    return TranscriptionJob(
        audio_path=audio,
        output_dir=tmp_path / "out",
        asr_backend="mlx",
        language="Chinese",
        diarization_enabled=True,
        diarization_num_speakers=2,
        pyannote_model="pyannote/speaker-diarization-community-1",
        hf_token=None,
    )


def test_parallel_path_overlaps_asr_and_pyannote(fake_job):
    """并发证据：pyannote 启动时间 < ASR 完成时间。

    用 monotonic timestamps 比 timeline 比 Event-based assert 更稳，不受
    GIL 调度抖动影响。
    """
    ts: dict[str, float] = {}

    def slow_asr(*args, **kwargs):
        ts["asr_start"] = time.monotonic()
        time.sleep(0.15)
        ts["asr_done"] = time.monotonic()
        return [TranscriptSegment(start=0, end=10, text="hello",
                                   speaker="SPEAKER_00", source="mlx")]

    def slow_diar(self_diar, audio_path):
        ts["pyannote_start"] = time.monotonic()
        time.sleep(0.15)
        ts["pyannote_done"] = time.monotonic()
        return [SpeakerTurn(start=0, end=10, speaker="SPEAKER_00")]

    fake_backend = MagicMock()
    fake_backend.transcribe = slow_asr

    with patch("liasse.transcribe_pipeline.create_asr_backend",
               return_value=fake_backend), \
         patch("liasse.diarization.PyannoteDiarizer.diarize",
               slow_diar):
        result = TranscribePipeline().run(fake_job)

    # 两者都跑过
    assert {"asr_start", "asr_done", "pyannote_start", "pyannote_done"} <= ts.keys()
    # 关键不变量：pyannote_start < asr_done（启动时 ASR 还没结束）
    # 串行版本下 pyannote_start ≈ asr_done + epsilon
    assert ts["pyannote_start"] < ts["asr_done"], (
        f"pyannote 必须在 ASR 完成前启动才算并行 — "
        f"pyannote_start={ts['pyannote_start']:.3f}, asr_done={ts['asr_done']:.3f}"
    )
    assert len(result.segments) == 1


def test_parallel_path_disables_internal_diarize(fake_job):
    """ASR backend 收到的 job 必须是 diarization_enabled=False（避免 mlx
    内部又装一遍 pyannote 形成两份模型驻留）。"""
    received_job = {"obj": None}

    def captured_create(*args, diarization_enabled=False, **kwargs):
        received_job["enabled"] = diarization_enabled
        m = MagicMock()
        m.transcribe = MagicMock(return_value=[
            TranscriptSegment(start=0, end=5, text="x", speaker="SPEAKER_00", source="mlx"),
        ])
        return m

    with patch("liasse.transcribe_pipeline.create_asr_backend",
               side_effect=captured_create), \
         patch("liasse.diarization.PyannoteDiarizer.diarize",
               return_value=[SpeakerTurn(start=0, end=5, speaker="SPEAKER_00")]):
        TranscribePipeline().run(fake_job)

    assert received_job["enabled"] is False, (
        "parallel path 必须传 diarization_enabled=False 给 backend"
    )


def test_parallel_path_falls_back_on_pyannote_failure(fake_job):
    """pyannote 抛错 → ASR 结果不丢，speaker 退化到 speaker_turns_from_segments。"""
    fake_backend = MagicMock()
    fake_backend.transcribe = MagicMock(return_value=[
        TranscriptSegment(start=0, end=5, text="hello",
                          speaker="SPEAKER_00", source="mlx"),
    ])

    def boom(self_diar, audio_path):
        raise RuntimeError("pyannote 网络挂了")

    with patch("liasse.transcribe_pipeline.create_asr_backend",
               return_value=fake_backend), \
         patch("liasse.diarization.PyannoteDiarizer.diarize", boom):
        result = TranscribePipeline().run(fake_job)

    # ASR 结果保留
    assert len(result.segments) == 1
    assert result.segments[0].text == "hello"
    # speaker_turns 落回 from-segments
    assert len(result.speaker_turns) == 1


def test_non_parallel_path_when_diarize_disabled(fake_job):
    """diarization_enabled=False 时走老路径，不开 thread。"""
    fake_job = TranscriptionJob(
        audio_path=fake_job.audio_path,
        output_dir=fake_job.output_dir,
        asr_backend="mlx",
        language="Chinese",
        diarization_enabled=False,  # 关键
    )

    pyannote_called = {"count": 0}

    def diar(self_diar, audio_path):
        pyannote_called["count"] += 1
        return []

    fake_backend = MagicMock()
    fake_backend.transcribe = MagicMock(return_value=[
        TranscriptSegment(start=0, end=5, text="hi",
                          speaker="SPEAKER_00", source="mlx"),
    ])

    with patch("liasse.transcribe_pipeline.create_asr_backend",
               return_value=fake_backend), \
         patch("liasse.diarization.PyannoteDiarizer.diarize", diar):
        TranscribePipeline().run(fake_job)

    assert pyannote_called["count"] == 0, "diarize off 时不应调 pyannote"


def test_parallel_path_aligns_segments_to_speaker_turns(fake_job):
    """pyannote 给的 turns 必须真的被 assign_speakers 用到 segments 上。"""
    fake_backend = MagicMock()
    fake_backend.transcribe = MagicMock(return_value=[
        TranscriptSegment(start=0, end=5, text="A 说",
                          speaker="SPEAKER_00", source="mlx"),
        TranscriptSegment(start=5, end=10, text="B 说",
                          speaker="SPEAKER_00", source="mlx"),
    ])

    turns = [
        SpeakerTurn(start=0, end=5, speaker="SPK_X"),
        SpeakerTurn(start=5, end=10, speaker="SPK_Y"),
    ]

    with patch("liasse.transcribe_pipeline.create_asr_backend",
               return_value=fake_backend), \
         patch("liasse.diarization.PyannoteDiarizer.diarize",
               return_value=turns):
        result = TranscribePipeline().run(fake_job)

    speakers = sorted(set(s.speaker for s in result.segments))
    assert speakers == ["SPK_X", "SPK_Y"], (
        f"alignment 应该把 turns 的 speaker 套到 segments 上，got {speakers}"
    )
