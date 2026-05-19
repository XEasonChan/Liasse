"""探活 Ollama 本机服务 + 模型是否已 pull。"""
from __future__ import annotations

import json
import socket
import urllib.request


def check_ollama() -> bool:
    """Ollama HTTP API 端口是否在监听。"""
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=0.5):
            return True
    except OSError:
        return False


def check_ollama_model(name: str) -> bool:
    """指定模型是否已通过 `ollama pull` 下载。前缀匹配兼容 qwen3:4b 和
    qwen3:4b@digest 这样的标签变体；但不匹配 qwen3:4b-instruct 之类的
    不同变体。"""
    if not check_ollama():
        return False
    try:
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        with opener.open("http://127.0.0.1:11434/api/tags", timeout=1.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for m in data.get("models", []):
            mname = m.get("name", "")
            if mname == name or mname.startswith(f"{name}@"):
                return True
        return False
    except Exception:
        return False
