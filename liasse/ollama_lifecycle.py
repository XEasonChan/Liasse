from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

_log = logging.getLogger(__name__)

OLLAMA_ENDPOINT = "http://127.0.0.1:11434"


class OllamaError(RuntimeError):
    pass


def unload_model(model: str, endpoint: str = OLLAMA_ENDPOINT) -> None:
    """强制 Ollama 立即卸载指定模型（POST keep_alive=0）。

    失败不抛——可能 Ollama 已经卸载了，或者服务断开了，吞掉错误避免污染上层流程。
    """
    payload = json.dumps({"model": model, "keep_alive": 0}).encode("utf-8")
    req = urllib.request.Request(
        f"{endpoint.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        _log.debug("unload_model 失败 model=%s endpoint=%s: %s", model, endpoint, exc)


@contextmanager
def loaded_model(model: str, keep_alive: str = "5m") -> Iterator[str]:
    """上下文管理器：yield 模型名；退出时如果 keep_alive='0' 则强制卸载。

    在 tight 内存场景下用 keep_alive='0'，避免阻塞下一个阶段。
    """
    try:
        yield model
    finally:
        if str(keep_alive) == "0":
            unload_model(model)


@dataclass
class OllamaClient:
    endpoint: str = OLLAMA_ENDPOINT
    timeout: int = 600

    def generate(self, model: str, prompt: str, num_ctx: int = 8192,
                 temperature: float = 0.3, keep_alive: str = "5m") -> str:
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive,
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint.rstrip('/')}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise OllamaError("无法连接本地 Ollama。请确认服务已启动。") from exc
        return str(data.get("response", "")).strip()

    def stream_chat(self, model: str, messages: list[dict[str, str]], num_ctx: int = 8192,
                    temperature: float = 0.4, keep_alive: str = "5m") -> Iterator[str]:
        payload = json.dumps({
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": keep_alive,
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.endpoint.rstrip('/')}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = obj.get("message") or {}
                    delta = msg.get("content")
                    if delta:
                        yield delta
                    if obj.get("done"):
                        return
        except urllib.error.URLError as exc:
            raise OllamaError("无法连接本地 Ollama。") from exc
