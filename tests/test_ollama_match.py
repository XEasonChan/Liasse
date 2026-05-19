from unittest.mock import patch, MagicMock

import json


def test_check_ollama_model_exact_match(monkeypatch):
    fake_response = json.dumps({
        "models": [
            {"name": "qwen3:4b-instruct"},  # 不应匹配 "qwen3:4b"
            {"name": "llama3:8b"},
        ]
    }).encode()

    from local_transcriber.services import ollama_health
    monkeypatch.setattr(ollama_health, "check_ollama", lambda: True)

    with patch("urllib.request.build_opener") as mock_opener:
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = fake_response
        mock_opener.return_value = opener
        assert ollama_health.check_ollama_model("qwen3:4b") is False


def test_check_ollama_model_exact_present(monkeypatch):
    fake_response = json.dumps({
        "models": [
            {"name": "qwen3:4b"},
        ]
    }).encode()

    from local_transcriber.services import ollama_health
    monkeypatch.setattr(ollama_health, "check_ollama", lambda: True)

    with patch("urllib.request.build_opener") as mock_opener:
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = fake_response
        mock_opener.return_value = opener
        assert ollama_health.check_ollama_model("qwen3:4b") is True


def test_check_ollama_model_with_digest(monkeypatch):
    # ollama list 输出有时带 @sha256 后缀
    fake_response = json.dumps({
        "models": [
            {"name": "qwen3:4b@sha256:abc123"},
        ]
    }).encode()

    from local_transcriber.services import ollama_health
    monkeypatch.setattr(ollama_health, "check_ollama", lambda: True)

    with patch("urllib.request.build_opener") as mock_opener:
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = fake_response
        mock_opener.return_value = opener
        assert ollama_health.check_ollama_model("qwen3:4b") is True
