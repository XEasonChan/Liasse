"""检查 HuggingFace 模型缓存 + 安装日志解析。"""
from __future__ import annotations

import importlib.util
import os
import time
from pathlib import Path
from typing import Any, Dict


_INSTALL_LOG_PATH = Path.home() / "Library" / "Logs" / "WhisperQwen" / "install.log"


def check_model_cache() -> Dict[str, bool]:
    """逐项检查 HF 模型缓存是否就绪。"""
    from ..hf_paths import is_downloaded
    return {
        "qwen3_asr_06b": is_downloaded("Qwen/Qwen3-ASR-0.6B"),
        "qwen3_asr_17b": is_downloaded("Qwen/Qwen3-ASR-1.7B"),
        "qwen3_aligner_06b": is_downloaded("Qwen/Qwen3-ForcedAligner-0.6B"),
        "pyannote_community1": is_downloaded("pyannote/speaker-diarization-community-1"),
    }


def check_runtime_ready() -> bool:
    """重依赖（mlx-qwen3-asr 链）是否装好。装好 = 可以上传任务跑转录。"""
    return importlib.util.find_spec("mlx_qwen3_asr") is not None


def read_install_progress() -> Dict[str, Any]:
    """解析 install.log，给前端展示后台 pip 进度。

    返回字段:
      ready: bool — runtime 已就绪（重依赖装完）
      running: bool — install.log 还在被更新（最近 60 秒有新内容）
      installed: int — 已 "Successfully installed" 的批次
      currently: str — 当前 collecting / downloading 的包名（最近一行抽出）
      tail: list[str] — 日志最后若干行，前端可直接展示
      log_path: str
    """
    ready = check_runtime_ready()
    info: Dict[str, Any] = {
        "ready": ready,
        "running": False,
        "installed": 0,
        "currently": "",
        "tail": [],
        "log_path": str(_INSTALL_LOG_PATH),
    }
    if not _INSTALL_LOG_PATH.exists():
        return info

    try:
        stat = _INSTALL_LOG_PATH.stat()
        info["running"] = (time.time() - stat.st_mtime) < 60 and not ready
        with _INSTALL_LOG_PATH.open("rb") as fp:
            try:
                fp.seek(-8192, os.SEEK_END)
            except OSError:
                fp.seek(0)
            data = fp.read().decode("utf-8", errors="replace")
    except OSError:
        return info

    lines = [ln for ln in data.splitlines() if ln.strip()]
    info["tail"] = lines[-12:]
    info["installed"] = sum(1 for ln in lines if ln.startswith("Successfully installed"))
    for ln in reversed(lines):
        if (
            ln.startswith("Collecting ")
            or ln.startswith("Downloading ")
            or ln.startswith("  Downloading ")
        ):
            token = ln.strip().split(" ", 2)
            info["currently"] = token[1] if len(token) > 1 else ln.strip()
            break
    return info
