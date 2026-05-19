from __future__ import annotations

from typing import Optional


def format_clock(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--:--"
    seconds = max(float(seconds), 0.0)
    whole = int(seconds)
    hours = whole // 3600
    minutes = (whole % 3600) // 60
    secs = whole % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_srt_time(seconds: Optional[float]) -> str:
    if seconds is None:
        seconds = 0.0
    seconds = max(float(seconds), 0.0)
    whole = int(seconds)
    millis = int(round((seconds - whole) * 1000))
    if millis == 1000:
        whole += 1
        millis = 0
    hours = whole // 3600
    minutes = (whole % 3600) // 60
    secs = whole % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
