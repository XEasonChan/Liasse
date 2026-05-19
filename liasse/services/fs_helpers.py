"""上传 / 重试时用到的小文件系统工具。"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional


def unique_path(target: Path) -> Path:
    """如果 target 已存在，在 stem 后加 -1, -2, ... 直到不冲突。"""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    n = 1
    while True:
        candidate = target.with_name(f"{stem}-{n}{suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def probe_audio_duration(path: Path) -> Optional[float]:
    """ffprobe 读音频时长（秒）。ffprobe 不在 PATH 或文件无效时返回 None。"""
    if not shutil.which("ffprobe"):
        return None
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if completed.returncode != 0:
            return None
        return float(completed.stdout.strip())
    except Exception:
        return None
