#!/usr/bin/env python3
"""Cut 5-minute samples from each audio in test_audio/ for the diarization
benchmark.

Coverage by design (mix of language + speaker gender combos):

  xiaojun_yaoshunyu.m4a     中文,2 男 (张小俊 vs 姚顺羽)         → s1..s5  (legacy 5 samples)
  luyu_niaoniao.mp3         中文,2 女 (鲁豫 vs 鸟鸟)            → luyu-1..4
  kedaibiao_weihui.mp3      中文,男+女 (柯达表 + 卫慧/类似组合)  → kd-1..4
  claude_design_lenny.mp3   英文,男+女 (Lenny + design guest)    → cd-1..4
  claude_engineer_lenny.mp3 英文,男+女 (Lenny + engineer guest)  → ce-1..4
  claude_product_lenny.mp3  英文,男+女 (Lenny + product guest)   → cp-1..4

Total: 5 + 20 = 25 samples × 5 min each.

Picking offsets: evenly spaced across the source audio, skipping 5 min
intro / 5 min outro to avoid Lenny intro music / podcast outro. ffmpeg
`-c copy` for m4a (no re-encode); mp3 sources kept as .mp3 (the pipeline
handles both via internal ffmpeg → wav conversion in diarization.py).

Idempotent: skips existing samples. Delete a sample file to re-cut.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent.parent
TEST_AUDIO = ROOT / "test_audio"
OUT = ROOT / "scripts" / "benchmark" / "samples"

SAMPLE_DUR = 300            # 5 min
EDGE_SKIP = 300             # skip first/last 5 min when picking offsets


@dataclass
class Source:
    file: str                # filename in test_audio/
    prefix: str              # output filename prefix
    n_cuts: int              # how many 5-min samples to cut
    legacy_names: List[str] | None = None  # if set, use these exact names instead of <prefix>-<i>

    @property
    def path(self) -> Path:
        return TEST_AUDIO / self.file


# 第一项是 legacy: 历史 5 个 sample 名字不动,GT/pred 都已落盘。
# 其它新增源每个切 4 个均匀间隔。
SOURCES: List[Source] = [
    Source(
        file="xiaojun_yaoshunyu.m4a",
        prefix="xj",
        n_cuts=5,
        legacy_names=[
            "s1-opening",      # 0:05:00
            "s2-deep-answer",  # 0:45:00
            "s3-back-forth",   # 1:20:00
            "s4-mid",          # 2:00:00
            "s5-late",         # 3:00:00
        ],
    ),
    Source(file="luyu_niaoniao.mp3",          prefix="luyu", n_cuts=4),
    Source(file="kedaibiao_weihui.mp3",       prefix="kd",   n_cuts=4),
    Source(file="claude_design_lenny.mp3",    prefix="cd",   n_cuts=4),
    Source(file="claude_engineer_lenny.mp3",  prefix="ce",   n_cuts=4),
    Source(file="claude_product_lenny.mp3",   prefix="cp",   n_cuts=4),
]

# Hardcoded offsets for the legacy xj source (must match prior cuts so GT
# alignment with existing .gt.json stays valid).
LEGACY_XJ_OFFSETS_SEC = [
    300,    # s1-opening      0:05:00
    2700,   # s2-deep-answer  0:45:00
    4800,   # s3-back-forth   1:20:00
    7200,   # s4-mid          2:00:00
    10800,  # s5-late         3:00:00
]


def _probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True,
    ).strip()
    return float(out)


def _spread_offsets(total_dur: float, n: int) -> List[float]:
    """Evenly spaced 5-min sample offsets, skipping EDGE_SKIP at both ends."""
    usable_start = float(EDGE_SKIP)
    usable_end = total_dur - EDGE_SKIP - SAMPLE_DUR
    if usable_end <= usable_start:
        usable_start, usable_end = 0.0, max(0.0, total_dur - SAMPLE_DUR)
    if n <= 1:
        return [usable_start]
    step = (usable_end - usable_start) / (n - 1)
    return [usable_start + i * step for i in range(n)]


def _format_ss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _cut(src: Path, dst: Path, start_sec: float) -> None:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", _format_ss(start_sec), "-t", str(SAMPLE_DUR),
        "-i", str(src),
        "-c", "copy",
        str(dst),
    ]
    subprocess.run(cmd, check=True)


def _names_and_offsets(source: Source) -> List[tuple[str, float]]:
    """Return [(name, start_sec), ...] for this source.

    For legacy xj source: use hardcoded names + offsets that match what
    was committed earlier (so existing .gt.json files stay valid).
    Else: evenly spread across the audio.
    """
    if source.legacy_names:
        names = source.legacy_names
        offsets = LEGACY_XJ_OFFSETS_SEC[:len(names)]
    else:
        dur = _probe_duration(source.path)
        names = [f"{source.prefix}-{i + 1}" for i in range(source.n_cuts)]
        offsets = _spread_offsets(dur, source.n_cuts)
    return list(zip(names, offsets))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    missing_sources: List[str] = []
    created = 0
    skipped = 0

    for source in SOURCES:
        if not source.path.exists():
            missing_sources.append(source.file)
            print(f"  ⚠ missing source {source.file}, skipping")
            continue
        ext = source.path.suffix  # .mp3 / .m4a — keep original (copy stream)
        for name, start in _names_and_offsets(source):
            dst = OUT / f"{name}{ext}"
            if dst.exists():
                print(f"  ✓ exists  {dst.name}")
                skipped += 1
                continue
            print(f"  cutting  {dst.name}  ({_format_ss(start)} +{SAMPLE_DUR}s)")
            try:
                _cut(source.path, dst, start)
                created += 1
            except subprocess.CalledProcessError as exc:
                print(f"  ✗ ffmpeg failed on {dst.name}: {exc}", file=sys.stderr)

    print(f"\n{created} created, {skipped} already present.")
    if missing_sources:
        print(f"⚠ {len(missing_sources)} missing source(s): {missing_sources}")
    return 0 if not missing_sources else 1


if __name__ == "__main__":
    sys.exit(main())
