"""增量逐字稿可见性的回归测试。

回应 cleanup item #8：用户上次跑长音频时，ASR 已经完成但 pyannote
diarization 阻塞 4 小时，期间前端拿不到任何 segments。链路本身（pipeline
→ progress queue → _apply_partial_transcript → TaskRow.transcript → /api
→ frontend）现在已经修好，这套测试守住它，防止以后某次 refactor 又
把它弄断。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from liasse.db import TaskRow, init_db, session_scope
from liasse.transcribe_pipeline import TranscribePipeline


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "tasks.db"
    monkeypatch.setenv("WHISPERQWEN_DB", str(db_path))
    init_db(db_path)
    yield db_path


def test_pipeline_emits_partial_transcript_on_chunk_completed(tmp_path):
    """pipeline._record_partial_chunk 必须把累积的 segments + raw text 推
    到 on_partial_transcript callback。这是 ASR-then-diarization 的唯一
    出口，断了用户就看不到中间结果。
    """
    received: list[dict] = []

    pipeline = TranscribePipeline(
        on_partial_transcript=lambda payload: received.append(payload),
    )

    pipeline._prepare_partial_transcript(
        job=_FakeJob(audio_stem="test", output_dir=tmp_path),
        output_dir=tmp_path,
    )

    # mlx-qwen3-asr 的 chunk_index 是 1-based（见 transcribe.py:703, 808）
    pipeline._record_partial_chunk({
        "chunk_index": 1,
        "chunk_offset_sec": 0.0,
        "chunk_duration_sec": 30.0,
        "text": "第一段转录文本",
    })
    pipeline._record_partial_chunk({
        "chunk_index": 2,
        "chunk_offset_sec": 30.0,
        "chunk_duration_sec": 25.0,
        "text": "第二段转录文本",
    })

    assert len(received) == 2, "每个 chunk_completed 都应触发 callback"

    last = received[-1]
    assert len(last["segments"]) == 2, "第二次 callback 应包含累积的 2 段"
    assert last["segments"][0].text == "第一段转录文本"
    assert last["segments"][1].text == "第二段转录文本"
    assert "第一段" in last["rawText"] and "第二段" in last["rawText"]
    assert last["rawTextPath"] and Path(last["rawTextPath"]).exists()


def test_pipeline_dedupes_repeated_chunk_index(tmp_path):
    """同一个 chunk_index 重复发来（mlx-qwen3-asr 在某些场景会重发），
    pipeline 必须去重，不能让前端看到的 segments 重复。"""
    received: list[dict] = []

    pipeline = TranscribePipeline(
        on_partial_transcript=lambda payload: received.append(payload),
    )
    pipeline._prepare_partial_transcript(
        job=_FakeJob(audio_stem="test", output_dir=tmp_path),
        output_dir=tmp_path,
    )

    # 用 1-based index，匹配 mlx-qwen3-asr 实际行为
    payload = {"chunk_index": 1, "chunk_offset_sec": 0.0,
               "chunk_duration_sec": 30.0, "text": "重复内容"}
    pipeline._record_partial_chunk(payload)
    pipeline._record_partial_chunk(payload)

    assert len(received) == 1, "重复 chunk_index 应被忽略，不再触发 callback"


def test_pipeline_ignores_empty_text_chunks(tmp_path):
    """空文本 chunk（mlx-qwen3-asr 偶尔会发）不应进 partial transcript。"""
    received: list[dict] = []

    pipeline = TranscribePipeline(
        on_partial_transcript=lambda payload: received.append(payload),
    )
    pipeline._prepare_partial_transcript(
        job=_FakeJob(audio_stem="test", output_dir=tmp_path),
        output_dir=tmp_path,
    )

    pipeline._record_partial_chunk({
        "chunk_index": 1, "chunk_offset_sec": 0.0,
        "chunk_duration_sec": 30.0, "text": "  ",
    })

    assert received == []


def test_task_row_to_api_exposes_partial_flag(isolated_db):
    """TaskRow.to_api() 返回的 transcript 字段必须保留 partial flag，前端
    才能区分「ASR 完成、diarization 进行中」和「全部完成」。"""
    with session_scope() as session:
        row = TaskRow(
            audio_path="/tmp/x.m4a",
            file_name="x.m4a",
            file_size_bytes=1000,
            status="running",
            transcript={
                "segments": [
                    {"id": "seg-0", "speaker": "SPEAKER_00",
                     "start": 0.0, "end": 5.0, "text": "测试"},
                ],
                "partial": True,
                "rawText": "测试",
                "rawTextPath": "/tmp/x-raw.partial.txt",
            },
        )
        session.add(row)
        session.commit()
        task_id = row.id

    with session_scope() as session:
        row = session.get(TaskRow, task_id)
        api = row.to_api()

    assert api["transcript"]["partial"] is True
    assert len(api["transcript"]["segments"]) == 1
    assert api["transcript"]["segments"][0]["text"] == "测试"


def test_task_runner_apply_partial_only_when_running(isolated_db):
    """_apply_partial_transcript 必须只在 status==running 时写库。如果任务
    已 done 或 failed，partial 消息应被丢弃（防止打乱最终结果）。"""
    from liasse.task_runner import TaskRunner

    # 真实构造 runner 会跑后台线程，这里只测私有方法。
    runner = TaskRunner.__new__(TaskRunner)

    with session_scope() as session:
        row = TaskRow(
            audio_path="/tmp/y.m4a",
            file_name="y.m4a",
            file_size_bytes=1000,
            status="done",
        )
        session.add(row)
        session.commit()
        task_id = row.id

    # 任务已 done，partial 消息应该被忽略
    runner._apply_partial_transcript(task_id, {
        "segments": [{"id": "seg-0", "speaker": "X", "start": 0.0,
                      "end": 5.0, "text": "迟到的 partial"}],
    })

    with session_scope() as session:
        row = session.get(TaskRow, task_id)
        assert row.transcript is None, "done 状态下不应被 partial 覆盖"


class _FakeJob:
    def __init__(self, audio_stem: str, output_dir: Path):
        self.audio_path = Path(output_dir) / f"{audio_stem}.m4a"
        self.output_dir = Path(output_dir)
