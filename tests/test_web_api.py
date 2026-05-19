from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "tasks.db"
    monkeypatch.setenv("WHISPERQWEN_DB", str(db_path))
    monkeypatch.setenv("WHISPERQWEN_DISABLE_RUNNER", "1")

    import importlib
    from liasse import web_app as web_app_module

    importlib.reload(web_app_module)
    fastapi_app = web_app_module.create_app()

    from fastapi.testclient import TestClient

    with TestClient(fastapi_app) as c:
        yield c


def _upload_fake_audio(client, name="sample.wav", body=b"FAKEAUDIO" * 64):
    config = {
        "asrModel": "Qwen/Qwen3-ASR-0.6B",
        "diarize": True,
        "numSpeakers": 2,
        "summarize": False,
        "language": "Chinese",
    }
    files = [("files", (name, io.BytesIO(body), "audio/wav"))]
    data = {"config": json.dumps(config)}
    resp = client.post("/api/tasks/upload", files=files, data=data)
    assert resp.status_code == 200, resp.text
    return resp.json()["tasks"][0]


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "checks" in body
    assert isinstance(body["checks"]["models"], dict)


def test_upload_creates_task(client):
    task = _upload_fake_audio(client, "interview.wav")
    assert task["status"] == "queued"
    assert task["fileName"] == "interview.wav"
    assert task["fileSizeBytes"] > 0
    assert task["config"]["speakerMode"] == "pyannote"
    assert task["config"]["diarize"] is True
    assert task["config"]["numSpeakers"] == 2
    assert task["progress"] == 0.0

    listing = client.get("/api/tasks").json()
    assert any(t["id"] == task["id"] for t in listing["tasks"])


def test_list_filter_by_status(client):
    _upload_fake_audio(client, "a.wav")
    _upload_fake_audio(client, "b.wav")
    listing = client.get("/api/tasks?status=queued").json()
    assert len(listing["tasks"]) == 2
    listing = client.get("/api/tasks?status=done").json()
    assert listing["tasks"] == []


def test_task_detail(client):
    task = _upload_fake_audio(client, "c.wav")
    resp = client.get(f"/api/tasks/{task['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == task["id"]

    resp = client.get("/api/tasks/nope-id")
    assert resp.status_code == 404


def test_edit_speaker_and_segment_persist(client):
    task = _upload_fake_audio(client, "d.wav")
    tid = task["id"]

    r = client.post(
        f"/api/tasks/{tid}/edits/speaker",
        json={"speakerId": "SPEAKER_00", "label": "主持人"},
    )
    assert r.status_code == 200
    r = client.post(
        f"/api/tasks/{tid}/edits/segment",
        json={"segmentId": "seg-1", "text": "改后的文字"},
    )
    assert r.status_code == 200

    detail = client.get(f"/api/tasks/{tid}").json()
    assert detail["edits"]["speakerLabels"]["SPEAKER_00"] == "主持人"
    assert detail["edits"]["segmentOverrides"]["seg-1"] == "改后的文字"


def test_delete_task(client):
    task = _upload_fake_audio(client, "e.wav")
    r = client.delete(f"/api/tasks/{task['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["deletedOutputs"] is False

    r = client.get(f"/api/tasks/{task['id']}")
    assert r.status_code == 404


def test_clear_completed(client):
    t1 = _upload_fake_audio(client, "f.wav")
    t2 = _upload_fake_audio(client, "g.wav")

    from liasse.db import TaskRow, session_scope

    with session_scope() as s:
        row = s.get(TaskRow, t1["id"])
        row.status = "done"
        s.commit()

    r = client.post("/api/tasks/clear-completed")
    assert r.status_code == 200
    assert r.json()["removed"] == 1
    remaining = client.get("/api/tasks").json()["tasks"]
    assert len(remaining) == 1
    assert remaining[0]["id"] == t2["id"]


def test_upload_rejects_invalid_config(client):
    files = [("files", ("x.wav", io.BytesIO(b"123"), "audio/wav"))]
    data = {"config": "not-json"}
    resp = client.post("/api/tasks/upload", files=files, data=data)
    assert resp.status_code == 400


def test_create_from_paths_creates_tasks(client, tmp_path):
    audio_a = tmp_path / "alpha.m4a"
    audio_a.write_bytes(b"FAKE_AUDIO" * 100)
    audio_b = tmp_path / "beta.wav"
    audio_b.write_bytes(b"WAV_DATA" * 80)

    payload = {
        "paths": [str(audio_a), str(audio_b)],
        "config": {
            "asrModel": "Qwen/Qwen3-ASR-0.6B",
            "diarize": True,
            "numSpeakers": 2,
            "summarize": False,
            "language": "Chinese",
        },
    }
    resp = client.post("/api/tasks/create-from-paths", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["tasks"]) == 2
    assert body["tasks"][0]["audioPath"] == str(audio_a)
    assert body["tasks"][0]["status"] == "queued"
    assert body["tasks"][0]["config"]["speakerMode"] == "pyannote"
    assert body["skipped"] == []


def test_create_from_paths_persists_three_speaker_modes(client, tmp_path):
    # 每个 mode 用独立 audio 文件：create-from-paths 现在对同一 audio_path
    # 有「未失败/停止」的活跃任务时会跳过（去重）。测试只关心 speakerMode 持久化。
    for mode in ("fast", "llm", "pyannote"):
        audio = tmp_path / f"mode-{mode}.wav"
        audio.write_bytes(b"data")
        payload = {
            "paths": [str(audio)],
            "config": {
                "asrModel": "Qwen/Qwen3-ASR-0.6B",
                "language": "Chinese",
                "speakerMode": mode,
                "numSpeakers": 2,
            },
        }
        resp = client.post("/api/tasks/create-from-paths", json=payload)
        assert resp.status_code == 200, resp.text
        task = resp.json()["tasks"][0]
        assert task["config"]["speakerMode"] == mode
        assert task["config"]["diarize"] is (mode == "pyannote")


def test_create_from_paths_dedups_active_audio_path(client, tmp_path):
    """同一路径上传第二次：第一次创建，第二次 skipped。回归：用户截图里
    同一个 cut-2min-mid.m4a 出现 2 条任务。"""
    audio = tmp_path / "dup.wav"
    audio.write_bytes(b"data")
    payload = {
        "paths": [str(audio)],
        "config": {"asrModel": "Qwen/Qwen3-ASR-0.6B", "language": "Chinese"},
    }
    first = client.post("/api/tasks/create-from-paths", json=payload).json()
    assert len(first["tasks"]) == 1 and not first["skipped"]

    second = client.post("/api/tasks/create-from-paths", json=payload).json()
    assert second["tasks"] == []
    assert len(second["skipped"]) == 1
    assert "已有任务" in second["skipped"][0]["reason"]


def test_create_from_paths_dedups_within_single_request(client, tmp_path):
    """同一请求里塞 2 个相同 path：只创建 1 个，另一个 skipped。"""
    audio = tmp_path / "same.wav"
    audio.write_bytes(b"data")
    payload = {
        "paths": [str(audio), str(audio)],
        "config": {"asrModel": "Qwen/Qwen3-ASR-0.6B", "language": "Chinese"},
    }
    resp = client.post("/api/tasks/create-from-paths", json=payload).json()
    assert len(resp["tasks"]) == 1
    assert len(resp["skipped"]) == 1


def test_create_from_paths_allows_repeat_after_deletion(client, tmp_path):
    """删掉旧任务后，同路径应能重新上传。"""
    from liasse.db import TaskRow, session_scope

    audio = tmp_path / "again.wav"
    audio.write_bytes(b"data")
    payload = {
        "paths": [str(audio)],
        "config": {"asrModel": "Qwen/Qwen3-ASR-0.6B", "language": "Chinese"},
    }
    first = client.post("/api/tasks/create-from-paths", json=payload).json()
    tid = first["tasks"][0]["id"]

    with session_scope() as s:
        row = s.get(TaskRow, tid)
        s.delete(row)
        s.commit()

    second = client.post("/api/tasks/create-from-paths", json=payload).json()
    assert len(second["tasks"]) == 1
    assert second["skipped"] == []


def test_create_from_paths_skips_missing(client, tmp_path):
    real = tmp_path / "real.wav"
    real.write_bytes(b"data")
    payload = {
        "paths": [str(real), "/no/such/file.wav"],
        "config": {"asrModel": "Qwen/Qwen3-ASR-0.6B", "language": "Chinese"},
    }
    resp = client.post("/api/tasks/create-from-paths", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tasks"]) == 1
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["path"] == "/no/such/file.wav"


def test_create_from_paths_empty_400(client):
    payload = {
        "paths": [],
        "config": {"asrModel": "Qwen/Qwen3-ASR-0.6B", "language": "Chinese"},
    }
    resp = client.post("/api/tasks/create-from-paths", json=payload)
    assert resp.status_code == 400


def test_open_path_rejects_path_outside_outputs(client, tmp_path, monkeypatch):
    bad = tmp_path / "outside.txt"
    bad.write_text("nope")
    resp = client.post("/api/open-path", json={"path": str(bad)})
    assert resp.status_code == 403


def test_open_path_accepts_outputs_subdir(client, monkeypatch):
    calls = []
    import subprocess

    def fake_run(args, **kwargs):
        calls.append(args)

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    from liasse import web_app as wa

    outputs = wa.OUTPUTS_DIR
    outputs.mkdir(parents=True, exist_ok=True)
    target = outputs / "should-exist"
    target.mkdir(exist_ok=True)

    resp = client.post("/api/open-path", json={"path": str(target)})
    assert resp.status_code == 200, resp.text
    assert calls and calls[0][0] == "open"


def test_retry_failed_task_requeues(client, tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"data" * 100)
    payload = {
        "paths": [str(audio)],
        "config": {"asrModel": "Qwen/Qwen3-ASR-0.6B", "language": "English"},
    }
    task = client.post("/api/tasks/create-from-paths", json=payload).json()["tasks"][0]

    from liasse.db import TaskRow, session_scope

    with session_scope() as s:
        row = s.get(TaskRow, task["id"])
        row.status = "failed"
        row.error_message = "boom"
        row.summary_text = "old summary that should be cleared"
        row.chat_context_digest = "old digest"
        s.commit()

    resp = client.post(f"/api/tasks/{task['id']}/retry")
    assert resp.status_code == 200
    refreshed = resp.json()
    assert refreshed["status"] == "queued"
    assert refreshed["progress"] == 0.0
    assert refreshed["errorMessage"] is None
    with session_scope() as s:
        row = s.get(TaskRow, task["id"])
        assert row.summary_text is None
        assert row.chat_context_digest is None


def test_retry_running_task_rejected(client, tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"data")
    payload = {
        "paths": [str(audio)],
        "config": {"asrModel": "Qwen/Qwen3-ASR-0.6B", "language": "English"},
    }
    task = client.post("/api/tasks/create-from-paths", json=payload).json()["tasks"][0]

    from liasse.db import TaskRow, session_scope

    with session_scope() as s:
        row = s.get(TaskRow, task["id"])
        row.status = "running"
        s.commit()

    resp = client.post(f"/api/tasks/{task['id']}/retry")
    assert resp.status_code == 400


def test_retry_missing_audio_rejected(client, tmp_path):
    audio = tmp_path / "vanish.wav"
    audio.write_bytes(b"data")
    payload = {
        "paths": [str(audio)],
        "config": {"asrModel": "Qwen/Qwen3-ASR-0.6B", "language": "English"},
    }
    task = client.post("/api/tasks/create-from-paths", json=payload).json()["tasks"][0]

    from liasse.db import TaskRow, session_scope

    with session_scope() as s:
        row = s.get(TaskRow, task["id"])
        row.status = "failed"
        s.commit()

    audio.unlink()
    resp = client.post(f"/api/tasks/{task['id']}/retry")
    assert resp.status_code == 400


def test_cleanup_orphans_marks_running_as_stopped(client, tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"data")
    payload = {
        "paths": [str(audio)],
        "config": {"asrModel": "Qwen/Qwen3-ASR-0.6B", "language": "English"},
    }
    task = client.post("/api/tasks/create-from-paths", json=payload).json()["tasks"][0]

    from liasse.db import TaskRow, session_scope
    from liasse.task_runner import TaskRunner
    import os

    with session_scope() as s:
        row = s.get(TaskRow, task["id"])
        row.status = "running"
        row.progress_stage = "正在转录"
        s.commit()

    db_path = Path(os.environ["WHISPERQWEN_DB"])
    runner = TaskRunner(db_path)
    runner._cleanup_orphans()

    with session_scope() as s:
        row = s.get(TaskRow, task["id"])
        assert row.status == "stopped"
        assert "interrupted" in (row.error_message or "").lower()


def test_task_runner_persists_partial_transcript(client, tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"data")
    payload = {
        "paths": [str(audio)],
        "config": {"asrModel": "Qwen/Qwen3-ASR-0.6B", "language": "English"},
    }
    task = client.post("/api/tasks/create-from-paths", json=payload).json()["tasks"][0]

    from liasse.db import TaskRow, session_scope
    from liasse.task_runner import TaskRunner
    import os

    with session_scope() as s:
        row = s.get(TaskRow, task["id"])
        row.status = "running"
        s.commit()

    runner = TaskRunner(Path(os.environ["WHISPERQWEN_DB"]))
    runner._apply_partial_transcript(
        task["id"],
        {
            "segments": [
                {
                    "id": "raw-0",
                    "speaker": "SPEAKER_00",
                    "start": 0.0,
                    "end": 2.0,
                    "text": "fallback text",
                }
            ],
            "rawText": "fallback text",
            "rawTextPath": str(tmp_path / "sample-raw.partial.txt"),
            "outputDir": str(tmp_path / "outputs"),
        },
    )

    with session_scope() as s:
        row = s.get(TaskRow, task["id"])
        assert row.transcript["partial"] is True
        assert row.transcript["rawText"] == "fallback text"
        assert row.transcript["segments"][0]["text"] == "fallback text"
        assert row.outputs["rawTextPath"].endswith("sample-raw.partial.txt")


def test_task_runner_finalize_persists_speaker_mode_warnings_and_suggested_labels(client, tmp_path):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"data")
    payload = {
        "paths": [str(audio)],
        "config": {
            "asrModel": "Qwen/Qwen3-ASR-0.6B",
            "language": "English",
            "speakerMode": "llm",
        },
    }
    task = client.post("/api/tasks/create-from-paths", json=payload).json()["tasks"][0]

    from liasse.db import TaskRow, session_scope
    from liasse.task_runner import TaskRunner
    import os

    with session_scope() as s:
        row = s.get(TaskRow, task["id"])
        row.status = "running"
        row.edits = {"speakerLabels": {"SPEAKER_00": "已改名"}, "segmentOverrides": {}}
        s.commit()

    runner = TaskRunner(Path(os.environ["WHISPERQWEN_DB"]))
    runner._finalize(
        task["id"],
        {
            "type": "done",
            "outputs": {},
            "segments": [
                {
                    "id": "seg-0",
                    "speaker": "SPEAKER_00",
                    "start": 0.0,
                    "end": 1.0,
                    "text": "hello",
                }
            ],
            "speakerModeEffective": "llm",
            "warnings": ["智能分离失败，已保留未分离逐字稿"],
            "suggestedSpeakerLabels": {
                "SPEAKER_00": "采访者",
                "SPEAKER_01": "受访者",
            },
        },
        elapsed_sec=1.0,
    )

    with session_scope() as s:
        row = s.get(TaskRow, task["id"])
        assert row.transcript["speakerModeEffective"] == "llm"
        assert row.transcript["warnings"] == ["智能分离失败，已保留未分离逐字稿"]
        assert row.edits["speakerLabels"]["SPEAKER_00"] == "已改名"
        assert row.edits["speakerLabels"]["SPEAKER_01"] == "受访者"


def test_health_returns_blockers_field(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "blockers" in body
    assert isinstance(body["blockers"], list)
    assert "asr_model" in body["checks"]
    assert "disk_free_gb" in body["checks"]


def test_chat_endpoint_uses_qa_engine(client, monkeypatch):
    """/chat 路由必须经过 QAEngine.answer（chat.py 已删除）。"""
    from liasse.db import session_scope, TaskRow

    task = _upload_fake_audio(client, "chat-target.wav")
    with session_scope() as s:
        row = s.get(TaskRow, task["id"])
        row.status = "completed"
        row.transcript = {
            "segments": [
                {"id": "seg-0", "speaker": "A", "start": 0.0, "end": 5.0,
                 "text": "我们讨论教育公平"},
                {"id": "seg-1", "speaker": "B", "start": 5.0, "end": 10.0,
                 "text": "资源分配是核心"},
            ]
        }
        s.commit()

    calls = {"answer": 0, "digest": 0}

    from liasse import qa_engine as qa_engine_module
    real_engine_cls = qa_engine_module.QAEngine

    class _SpyEngine(real_engine_cls):
        def answer(self, question, history, top_k=None, client=None):
            calls["answer"] += 1
            yield "测试"
            yield "回答"

    monkeypatch.setattr(qa_engine_module, "QAEngine", _SpyEngine)

    # chat.py 已删除；以前的 generate_digest spy 不再需要——模块本身不存在
    # 就是最强的「不可能调用」保证。验证一下 import 失败：
    import importlib
    try:
        importlib.import_module("liasse.chat")
        raise AssertionError("liasse.chat 应该已被删除")
    except ModuleNotFoundError:
        pass

    resp = client.post(f"/api/tasks/{task['id']}/chat", json={"message": "教育公平"})
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert "event: delta" in body
    assert "测试" in body
    assert "event: done" in body
    assert calls["answer"] == 1
    assert calls["digest"] == 0


def test_chat_endpoint_rejects_empty_transcript(client):
    from liasse.db import session_scope, TaskRow

    task = _upload_fake_audio(client, "empty-chat.wav")
    with session_scope() as s:
        row = s.get(TaskRow, task["id"])
        row.status = "completed"
        row.transcript = {"segments": []}
        s.commit()

    resp = client.post(f"/api/tasks/{task['id']}/chat", json={"message": "你好"})
    assert resp.status_code == 400


def test_delete_task_removes_uploaded_audio_copy(client, tmp_path, monkeypatch):
    """delete_outputs=true 应同时清掉 outputs/uploaded_audio 下的上传副本，
    而不只是 task.outputs 目录。原生路径模式（audio_path 不在 uploaded_audio
    下）保护原始音频不被误删。"""
    from liasse import web_app as wa

    monkeypatch.setattr(wa, "OUTPUTS_DIR", tmp_path)
    upload_dir = tmp_path / "uploaded_audio"
    upload_dir.mkdir(parents=True, exist_ok=True)
    fake_copy = upload_dir / "uploaded.m4a"
    fake_copy.write_bytes(b"FAKE")

    outside = tmp_path / "outside.m4a"
    outside.write_bytes(b"REAL")

    from liasse.db import TaskRow, session_scope

    with session_scope() as s:
        s.add(TaskRow(
            id="t-upload",
            audio_path=str(fake_copy),
            file_name="uploaded.m4a",
            status="done",
            config={},
        ))
        s.add(TaskRow(
            id="t-native",
            audio_path=str(outside),
            file_name="outside.m4a",
            status="done",
            config={},
        ))
        s.commit()

    resp = client.delete("/api/tasks/t-upload?delete_outputs=true")
    assert resp.status_code == 200
    assert not fake_copy.exists(), "uploaded_audio 副本必须随 delete_outputs=true 一起清掉"

    resp = client.delete("/api/tasks/t-native?delete_outputs=true")
    assert resp.status_code == 200
    assert outside.exists(), "原生路径模式下原始音频绝对不能被删"


def test_delete_task_keeps_uploaded_when_delete_outputs_false(client, tmp_path, monkeypatch):
    """delete_outputs=false（默认）只移除 DB 记录，副本和 outputs 都保留。"""
    from liasse import web_app as wa

    monkeypatch.setattr(wa, "OUTPUTS_DIR", tmp_path)
    upload_dir = tmp_path / "uploaded_audio"
    upload_dir.mkdir(parents=True, exist_ok=True)
    fake_copy = upload_dir / "keep.m4a"
    fake_copy.write_bytes(b"FAKE")

    from liasse.db import TaskRow, session_scope

    with session_scope() as s:
        s.add(TaskRow(
            id="t-keep",
            audio_path=str(fake_copy),
            file_name="keep.m4a",
            status="done",
            config={},
        ))
        s.commit()

    resp = client.delete("/api/tasks/t-keep")
    assert resp.status_code == 200
    assert fake_copy.exists(), "delete_outputs=false 时副本必须保留"
