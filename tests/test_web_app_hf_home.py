import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_health_finds_model_under_hf_home(monkeypatch, tmp_path):
    fake_hub = tmp_path / "hub"
    (fake_hub / "models--Qwen--Qwen3-ASR-0.6B").mkdir(parents=True)
    monkeypatch.setenv("HF_HOME", str(tmp_path))

    import importlib
    from liasse import web_app
    importlib.reload(web_app)
    client = TestClient(web_app.app)

    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["checks"]["asr_model"] is True


def test_models_endpoint_finds_model_under_hf_home(monkeypatch, tmp_path):
    fake_hub = tmp_path / "hub"
    (fake_hub / "models--Qwen--Qwen3-ASR-0.6B").mkdir(parents=True)
    monkeypatch.setenv("HF_HOME", str(tmp_path))

    import importlib
    from liasse import web_app
    importlib.reload(web_app)
    client = TestClient(web_app.app)

    resp = client.get("/api/models")
    assert resp.status_code == 200
    items = {m["id"]: m for m in resp.json()["models"]}
    assert items["Qwen/Qwen3-ASR-0.6B"]["downloaded"] is True


def test_health_respects_empty_hf_home(monkeypatch, tmp_path):
    """HF_HOME 指向一个空目录时，即使 ~/.cache 里有模型也应报告未下载。
    这是验证 hf_paths 真的被尊重了，而不是巧合命中默认路径。"""
    # tmp_path 下没有 hub/ 子目录，更没有任何模型
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)

    import importlib
    from liasse import web_app
    importlib.reload(web_app)
    client = TestClient(web_app.app)

    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["checks"]["asr_model"] is False
    assert data["checks"]["aligner_model"] is False
    assert data["checks"]["pyannote_model"] is False


def test_models_endpoint_respects_empty_hf_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)

    import importlib
    from liasse import web_app
    importlib.reload(web_app)
    client = TestClient(web_app.app)

    resp = client.get("/api/models")
    assert resp.status_code == 200
    items = {m["id"]: m for m in resp.json()["models"]}
    assert items["Qwen/Qwen3-ASR-0.6B"]["downloaded"] is False
    assert items["Qwen/Qwen3-ForcedAligner-0.6B"]["downloaded"] is False
    assert items["Qwen/Qwen3-ASR-1.7B"]["downloaded"] is False
    assert items["pyannote/speaker-diarization-community-1"]["downloaded"] is False
