from __future__ import annotations

import pytest

from local_transcriber.models import TranscriptionJob, TranscriptSegment
from local_transcriber.pipeline import LocalTranscriptionPipeline


class FakeChunkedASRBackend:
    def transcribe(self, audio_path, language, on_progress=None):
        if on_progress is not None:
            on_progress({"event": "chunks_prepared", "total_chunks": 4, "progress": 0.0})
            on_progress({"event": "chunk_completed", "chunk_index": 1, "total_chunks": 4, "progress": 0.25})
            on_progress({"event": "chunk_completed", "chunk_index": 2, "total_chunks": 4, "progress": 0.50})
            on_progress({"event": "completed", "total_chunks": 4, "progress": 1.0})
        return [
            TranscriptSegment(
                start=0.0,
                end=2.0,
                speaker="SPEAKER_00",
                text="测试进度回调",
            )
        ]


def test_pipeline_maps_chunk_progress_to_precise_task_progress(tmp_path, monkeypatch):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"fake audio")
    events = []

    monkeypatch.setattr(
        "local_transcriber.pipeline.create_asr_backend",
        lambda **_: FakeChunkedASRBackend(),
    )

    pipeline = LocalTranscriptionPipeline(
        on_progress=lambda message, value: events.append((message, value))
    )
    pipeline.run(
        TranscriptionJob(
            audio_path=audio_path,
            output_dir=tmp_path / "outputs",
            asr_backend="mlx",
            diarization_enabled=False,
            summary_enabled=False,
        )
    )

    assert ("正在转录音频 1/4", pytest.approx(0.235)) in events
    assert ("正在转录音频 2/4", pytest.approx(0.43)) in events
    assert events[-1] == ("完成", 1.0)
