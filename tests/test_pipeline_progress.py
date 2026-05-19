from __future__ import annotations

import pytest

from local_transcriber.models import TranscriptionJob, TranscriptSegment
from local_transcriber.transcribe_pipeline import TranscribePipeline


class FakeChunkedASRBackend:
    def transcribe(self, audio_path, language, on_progress=None):
        if on_progress is not None:
            on_progress({"event": "chunks_prepared", "total_chunks": 4, "progress": 0.0})
            on_progress({
                "event": "chunk_completed",
                "chunk_index": 1,
                "total_chunks": 4,
                "chunk_offset_sec": 0.0,
                "chunk_duration_sec": 2.0,
                "progress": 0.25,
                "text": "第一段原始文本",
            })
            on_progress({
                "event": "chunk_completed",
                "chunk_index": 2,
                "total_chunks": 4,
                "chunk_offset_sec": 2.0,
                "chunk_duration_sec": 2.0,
                "progress": 0.50,
                "text": "第二段原始文本",
            })
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
        "local_transcriber.transcribe_pipeline.create_asr_backend",
        lambda **_: FakeChunkedASRBackend(),
    )

    pipeline = TranscribePipeline(
        on_progress=lambda message, value: events.append((message, value))
    )
    pipeline.run(
        TranscriptionJob(
            audio_path=audio_path,
            output_dir=tmp_path / "outputs",
            asr_backend="mlx",
            diarization_enabled=False,
        )
    )

    assert ("正在转录音频 1/4", pytest.approx(0.235)) in events
    assert ("正在转录音频 2/4", pytest.approx(0.43)) in events
    assert events[-1] == ("完成", 1.0)


def test_pipeline_emits_and_writes_partial_raw_transcript(tmp_path, monkeypatch):
    audio_path = tmp_path / "sample.wav"
    audio_path.write_bytes(b"fake audio")
    partials = []

    monkeypatch.setattr(
        "local_transcriber.transcribe_pipeline.create_asr_backend",
        lambda **_: FakeChunkedASRBackend(),
    )

    pipeline = TranscribePipeline(
        on_partial_transcript=lambda payload: partials.append(payload)
    )
    pipeline.run(
        TranscriptionJob(
            audio_path=audio_path,
            output_dir=tmp_path / "outputs",
            asr_backend="mlx",
            diarization_enabled=False,
        )
    )

    assert len(partials) == 2
    assert partials[-1]["rawText"] == "第一段原始文本\n第二段原始文本"
    assert [seg.text for seg in partials[-1]["segments"]] == [
        "第一段原始文本",
        "第二段原始文本",
    ]
    raw_path = tmp_path / "outputs"
    partial_files = list(raw_path.glob("sample-*/sample-raw.partial.txt"))
    assert len(partial_files) == 1
    assert partial_files[0].read_text(encoding="utf-8") == partials[-1]["rawText"]
