import os
from pathlib import Path

import pytest

from local_transcriber.hf_paths import hub_dir, model_dir


def test_hub_dir_default(monkeypatch):
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    expected = Path.home() / ".cache" / "huggingface" / "hub"
    assert hub_dir() == expected


def test_hub_dir_respects_hf_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.delenv("HUGGINGFACE_HUB_CACHE", raising=False)
    assert hub_dir() == tmp_path / "hub"


def test_hub_dir_respects_hub_cache(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", str(tmp_path / "hub"))
    assert hub_dir() == tmp_path / "hub"


def test_model_dir_resolves_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert model_dir("Qwen/Qwen3-ASR-0.6B") == tmp_path / "hub" / "models--Qwen--Qwen3-ASR-0.6B"
