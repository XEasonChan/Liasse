from __future__ import annotations

import os
from pathlib import Path


def hub_dir() -> Path:
    """返回 huggingface hub 缓存目录。

    优先级：HUGGINGFACE_HUB_CACHE > HF_HOME/hub > ~/.cache/huggingface/hub
    与 huggingface_hub 库的解析顺序一致。
    """
    explicit = os.environ.get("HUGGINGFACE_HUB_CACHE")
    if explicit:
        return Path(explicit).expanduser()
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home).expanduser() / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def model_dir(repo_id: str) -> Path:
    """给定 repo_id (e.g. Qwen/Qwen3-ASR-0.6B) 返回它在 hub 下的本地目录。"""
    return hub_dir() / f"models--{repo_id.replace('/', '--')}"


def is_downloaded(repo_id: str) -> bool:
    return model_dir(repo_id).exists()
