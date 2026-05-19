#!/usr/bin/env python3
"""从 test_audio/ll7qIcIWWGFSsORHr4yY-UuqAe8h.m4a 切 5 个 5 分钟样本。

源音频是 3h50m 的访谈，全程双人对话。挑了 5 个不同时间段覆盖多样场景：

  s1-opening       0:05:00-0:10:00  开场，研究者较多提问
  s2-deep-answer   0:45:00-0:50:00  受访者长答为主
  s3-back-forth    1:20:00-1:25:00  问答交替密集
  s4-mid           2:00:00-2:05:00  中段，节奏平稳
  s5-late          3:00:00-3:05:00  后段，可能语速加快

每段 5 分钟。用 ffmpeg -c copy 不重编码。samples/ gitignored。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = ROOT / "test_audio" / "ll7qIcIWWGFSsORHr4yY-UuqAe8h.m4a"
OUT = ROOT / "scripts" / "benchmark" / "samples"

SAMPLES = [
    ("s1-opening",     "00:05:00", 300),
    ("s2-deep-answer", "00:45:00", 300),
    ("s3-back-forth",  "01:20:00", 300),
    ("s4-mid",         "02:00:00", 300),
    ("s5-late",        "03:00:00", 300),
]


def main() -> int:
    if not SOURCE.exists():
        print(f"ERROR: source not found: {SOURCE}", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for name, start, dur in SAMPLES:
        dst = OUT / f"{name}.m4a"
        if dst.exists():
            print(f"  ✓ exists  {dst.name}")
            continue
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", start, "-t", str(dur),
            "-i", str(SOURCE),
            "-c", "copy",
            str(dst),
        ]
        print(f"  cutting   {dst.name} ({start} +{dur}s)")
        subprocess.run(cmd, check=True)
    print(f"\n{len(SAMPLES)} samples in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
