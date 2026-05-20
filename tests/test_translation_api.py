"""翻译 + 词库 API 集成测试。

启 FastAPI 测试 client,monkeypatch WHISPERQWEN_DB 让数据库走 tmp_path。
Ollama 全部 mock,无网络。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "tasks.db"
    outputs_dir = tmp_path / "outputs"
    monkeypatch.setenv("WHISPERQWEN_DB", str(db_path))
    monkeypatch.setenv("WHISPERQWEN_DISABLE_RUNNER", "1")
    monkeypatch.setenv("WHISPERQWEN_OUTPUTS_DIR", str(outputs_dir))

    import importlib

    from liasse import web_app as web_app_module
    importlib.reload(web_app_module)
    # web_app 在 import 时把 OUTPUTS_DIR 锁死到 ROOT/outputs;手动改成 tmp。
    web_app_module.OUTPUTS_DIR = outputs_dir
    outputs_dir.mkdir(parents=True, exist_ok=True)
    fastapi_app = web_app_module.create_app()

    with TestClient(fastapi_app) as c:
        yield c


def _seed_done_task(task_id="t-trans", segments=None):
    """绕过 upload,直接 SQL 插一个 done 任务方便测试。"""
    from liasse.db import TaskRow, session_scope
    if segments is None:
        segments = [
            {"id": 1, "start": 0, "end": 5, "speaker": "SPEAKER_00", "text": "原告反对"},
            {"id": 2, "start": 5, "end": 10, "speaker": "SPEAKER_01", "text": "被告同意"},
        ]
    with session_scope() as s:
        row = TaskRow(
            id=task_id,
            audio_path="/tmp/_unit.m4a",
            file_name="_unit.m4a",
            file_size_bytes=1,
            status="done",
            transcript={"segments": segments},
            config={"speakerMode": "fast"},
        )
        s.merge(row)
        s.commit()
    return task_id


# ---------- 词库 CRUD ----------

def test_glossary_crud_lifecycle(client):
    # create
    resp = client.post("/api/glossaries", json={
        "name": "law",
        "sourceLang": "Chinese",
        "targetLang": "English",
        "entries": [{"source": "原告", "target": "plaintiff"}],
    })
    assert resp.status_code == 200, resp.text

    # list
    resp = client.get("/api/glossaries")
    assert resp.status_code == 200
    assert "law" in resp.json().get("names", [])

    # get
    resp = client.get("/api/glossaries/law")
    assert resp.json()["entries"][0]["source"] == "原告"

    # update via PUT
    resp = client.put("/api/glossaries/law", json={
        "name": "law", "sourceLang": "Chinese", "targetLang": "English",
        "entries": [
            {"source": "原告", "target": "plaintiff"},
            {"source": "被告", "target": "defendant"},
        ],
    })
    assert resp.status_code == 200
    assert len(client.get("/api/glossaries/law").json()["entries"]) == 2

    # delete
    resp = client.delete("/api/glossaries/law")
    assert resp.status_code == 200
    assert client.get("/api/glossaries/law").status_code == 404


def test_glossary_invalid_name(client):
    resp = client.post("/api/glossaries", json={"name": "../bad", "entries": []})
    assert resp.status_code in (400, 422)


def test_put_glossary_path_body_name_mismatch(client):
    client.post("/api/glossaries", json={"name": "law", "entries": []})
    resp = client.put("/api/glossaries/law", json={"name": "other", "entries": []})
    assert resp.status_code == 400


# ---------- 翻译触发 ----------

def test_translate_task_endpoint_persists_result(client):
    _seed_done_task()
    fake_resp = json.dumps({"translations": [
        {"id": 1, "translation": "Plaintiff objects"},
        {"id": 2, "translation": "Defendant agrees"},
    ]})
    with patch("liasse.routers.translation.OllamaClient") as M:
        M.return_value.generate.return_value = fake_resp
        resp = client.post("/api/tasks/t-trans/translate", json={"target": "English"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["target"] == "English"
    assert data["segments"][0]["translation"] == "Plaintiff objects"

    # 再 GET task,translations 应已持久化
    from liasse.db import TaskRow, session_scope
    with session_scope() as s:
        row = s.get(TaskRow, "t-trans")
        assert "English" in (row.translations or {})


def test_translate_task_with_unknown_glossary_404(client):
    _seed_done_task("t-gloss-miss")
    resp = client.post(
        "/api/tasks/t-gloss-miss/translate",
        json={"target": "English", "glossaryName": "does-not-exist"},
    )
    assert resp.status_code == 404


def test_translate_task_not_done_409(client):
    from liasse.db import TaskRow, session_scope
    with session_scope() as s:
        s.merge(TaskRow(
            id="t-running",
            audio_path="/x.m4a",
            file_name="x.m4a",
            file_size_bytes=1,
            status="running",
            transcript={"segments": [
                {"id": 1, "start": 0, "end": 1, "text": "x", "speaker": "A"},
            ]},
            config={},
        ))
        s.commit()
    resp = client.post("/api/tasks/t-running/translate", json={"target": "English"})
    assert resp.status_code == 409


def test_translate_task_no_segments_409(client):
    from liasse.db import TaskRow, session_scope
    with session_scope() as s:
        s.merge(TaskRow(
            id="t-empty",
            audio_path="/x.m4a",
            file_name="x.m4a",
            file_size_bytes=1,
            status="done",
            transcript={"segments": []},
            config={},
        ))
        s.commit()
    resp = client.post("/api/tasks/t-empty/translate", json={"target": "English"})
    assert resp.status_code == 409


def test_translate_task_missing_404(client):
    resp = client.post("/api/tasks/does-not-exist/translate", json={"target": "English"})
    assert resp.status_code == 404


def test_translate_task_ollama_malformed_502(client):
    _seed_done_task("t-bad-json")
    with patch("liasse.routers.translation.OllamaClient") as M:
        M.return_value.generate.return_value = "this is not JSON at all"
        resp = client.post("/api/tasks/t-bad-json/translate", json={"target": "English"})
    assert resp.status_code == 502


# ---------- 双语 export ----------

def test_export_bilingual_404_missing_task(client):
    resp = client.get("/api/tasks/nope/export-bilingual?target=English")
    assert resp.status_code == 404


def test_export_bilingual_409_when_no_translation(client):
    _seed_done_task("t-no-trans")
    resp = client.get("/api/tasks/t-no-trans/export-bilingual?target=English")
    assert resp.status_code == 409


def test_export_bilingual_200_returns_markdown(client):
    _seed_done_task("t-bi-export")
    # 先注入一个翻译结果
    from liasse.db import TaskRow, session_scope
    with session_scope() as s:
        row = s.get(TaskRow, "t-bi-export")
        row.translations = {
            "English": {
                "target": "English",
                "model": "qwen3:4b",
                "segments": [
                    {"id": 1, "translation": "Plaintiff objects"},
                    {"id": 2, "translation": "Defendant agrees"},
                ],
                "generatedAt": "2026-05-19T00:00:00Z",
            }
        }
        s.commit()
    resp = client.get("/api/tasks/t-bi-export/export-bilingual?target=English")
    assert resp.status_code == 200
    assert "原告反对" in resp.text
    assert "Plaintiff objects" in resp.text
    assert resp.headers["content-type"].startswith("text/markdown")
