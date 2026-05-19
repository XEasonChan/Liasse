import json
from unittest.mock import MagicMock, patch

from liasse.ollama_lifecycle import (
    OllamaClient,
    unload_model,
    loaded_model,
)


def _mock_response(body: dict):
    resp = MagicMock()
    resp.__enter__ = lambda self: resp
    resp.__exit__ = lambda *a: None
    resp.read.return_value = json.dumps(body).encode("utf-8")
    return resp


def test_unload_sends_keep_alive_zero():
    with patch("liasse.ollama_lifecycle.urllib.request.urlopen") as op:
        op.return_value = _mock_response({"done": True})
        unload_model("qwen3:8b")
    args, _ = op.call_args
    req = args[0]
    body = json.loads(req.data.decode("utf-8"))
    assert body["model"] == "qwen3:8b"
    assert body["keep_alive"] == 0


def test_unload_swallows_connection_errors():
    import urllib.error
    with patch("liasse.ollama_lifecycle.urllib.request.urlopen",
               side_effect=urllib.error.URLError("connection refused")):
        # 不应抛
        unload_model("qwen3:8b")


def test_loaded_model_context_unloads_on_exit_when_keep_alive_0():
    with patch("liasse.ollama_lifecycle.unload_model") as un:
        with loaded_model("qwen3:8b", keep_alive="0"):
            pass
        un.assert_called_once_with("qwen3:8b")


def test_loaded_model_does_not_unload_when_keep_alive_set():
    with patch("liasse.ollama_lifecycle.unload_model") as un:
        with loaded_model("qwen3:8b", keep_alive="5m"):
            pass
        un.assert_not_called()


def test_generate_sends_payload():
    client = OllamaClient()
    with patch("liasse.ollama_lifecycle.urllib.request.urlopen") as op:
        op.return_value = _mock_response({"response": "你好"})
        out = client.generate(model="qwen3:4b", prompt="hi", num_ctx=4096)
    assert out == "你好"
    body = json.loads(op.call_args[0][0].data.decode("utf-8"))
    assert body["options"]["num_ctx"] == 4096
