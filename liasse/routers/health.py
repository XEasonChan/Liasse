"""健康检查 + 安装进度路由。

- GET /api/health         — 一次性返回 ASR / aligner / pyannote / ffmpeg /
                            Ollama / Qwen3:4b / disk / HF token 全套体检结果
- GET /api/install/progress — 解析后台 pip 安装日志的尾部，给 onboarding UI
                            实时反馈

依赖：services 模块（不依赖 DB / runner）。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List

from fastapi import APIRouter

from ..services import (
    check_model_cache,
    check_ollama,
    check_ollama_model,
    check_runtime_ready,
    read_install_progress,
)


router = APIRouter()

OUTPUTS_DIR = Path(os.environ.get("WHISPERQWEN_OUTPUTS_DIR", "outputs"))


@router.get("/api/health")
def health() -> dict:
    from ..hf_paths import is_downloaded

    asr_ok = is_downloaded("Qwen/Qwen3-ASR-0.6B")
    aligner_ok = is_downloaded("Qwen/Qwen3-ForcedAligner-0.6B")
    pyannote_ok = is_downloaded("pyannote/speaker-diarization-community-1")
    ollama_up = check_ollama()
    qwen4b_ok = check_ollama_model("qwen3:4b") if ollama_up else False
    runtime_ready = check_runtime_ready()
    hf_token_set = bool(
        os.environ.get("HF_TOKEN")
        or os.environ.get("PYANNOTE_AUTH_TOKEN")
        or os.environ.get("HUGGINGFACE_TOKEN")
    )
    try:
        usage = shutil.disk_usage(str(OUTPUTS_DIR))
        disk_free_gb = round(usage.free / (1024 ** 3), 1)
    except OSError:
        disk_free_gb = None

    blockers: List[str] = []
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        blockers.append("ffmpeg")
    if not asr_ok:
        blockers.append("asr_model")
    if not runtime_ready:
        blockers.append("runtime")

    return {
        "ok": not blockers,
        "blockers": blockers,
        "runtime_ready": runtime_ready,
        "checks": {
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "ffprobe": bool(shutil.which("ffprobe")),
            "ollama": ollama_up,
            "hf_token": hf_token_set,
            "asr_model": asr_ok,
            "aligner_model": aligner_ok,
            "pyannote_model": pyannote_ok,
            "qwen3_4b_model": qwen4b_ok,
            "runtime_ready": runtime_ready,
            "disk_free_gb": disk_free_gb,
            "models": check_model_cache(),
        },
    }


@router.get("/api/install/progress")
def install_progress() -> dict:
    return read_install_progress()
