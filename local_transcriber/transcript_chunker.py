from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Set

from .models import TranscriptSegment
from .timefmt import format_clock


@dataclass
class Chunk:
    index: int
    text: str
    segment_ids: List[int]
    start_time: float
    end_time: float
    speaker_set: Set[str] = field(default_factory=set)


def normalize_to_two_speakers(segments: List[TranscriptSegment]) -> List[TranscriptSegment]:
    """1对1 访谈：保留时长最多的 2 个 speaker，其余按时间邻近合并。"""
    if not segments:
        return segments

    durations: dict = defaultdict(float)
    for s in segments:
        if s.start is not None and s.end is not None:
            durations[s.speaker] += s.end - s.start

    if len(durations) <= 2:
        return list(segments)

    top_two = sorted(durations.items(), key=lambda kv: -kv[1])[:2]
    keep = {name for name, _ in top_two}

    out: List[TranscriptSegment] = []
    for i, s in enumerate(segments):
        if s.speaker in keep:
            out.append(s)
            continue
        # 找时间上最邻近的 keep 中的 speaker
        neighbor = _nearest_kept_speaker(segments, i, keep)
        out.append(TranscriptSegment(
            start=s.start, end=s.end, text=s.text,
            speaker=neighbor, confidence=s.confidence, source=s.source,
        ))
    return out


def _nearest_kept_speaker(segments: List[TranscriptSegment], i: int, keep: Set[str]) -> str:
    # 向前找
    for j in range(i - 1, -1, -1):
        if segments[j].speaker in keep:
            return segments[j].speaker
    # 向后找
    for j in range(i + 1, len(segments)):
        if segments[j].speaker in keep:
            return segments[j].speaker
    raise AssertionError("unreachable: keep is built from segments so at least one match must exist")


def chunk_interview(
    segments: List[TranscriptSegment],
    target_chars: int = 5000,
    max_chars: int = 6500,
    silence_split_seconds: float = 3.0,
) -> List[Chunk]:
    """1对1 访谈分块：尊重发言人轮次 + 长静默 + 字符上限。

    默认值理由：
    - target_chars=5000：qwen3:4b/8b 在 ~2500 token 输入下 L1 抽取质量稳定
    - max_chars=6500：硬上限，超过这个值 8K context 会被 prompt 模板挤爆
    - silence_split_seconds=3.0：访谈里典型话题切换前的停顿；< 3s 多是正常呼吸/思考
    """
    segments = normalize_to_two_speakers(segments)
    if not segments:
        return []

    chunks: List[Chunk] = []
    cur_lines: List[str] = []
    cur_ids: List[int] = []
    cur_chars = 0
    cur_start: float = segments[0].start or 0.0
    cur_end: float = segments[0].end or 0.0
    cur_speakers: Set[str] = set()
    last_end: float = segments[0].start or 0.0

    def flush():
        nonlocal cur_lines, cur_ids, cur_chars, cur_start, cur_end, cur_speakers
        if not cur_lines:
            return
        chunks.append(Chunk(
            index=len(chunks),
            text="\n".join(cur_lines),
            segment_ids=list(cur_ids),
            start_time=cur_start,
            end_time=cur_end,
            speaker_set=set(cur_speakers),
        ))
        cur_lines = []
        cur_ids = []
        cur_chars = 0
        cur_speakers = set()

    for i, seg in enumerate(segments):
        seg_start = seg.start if seg.start is not None else last_end
        seg_end = seg.end if seg.end is not None else seg_start
        line = f"[{format_clock(seg_start)}-{format_clock(seg_end)}] {seg.speaker}: {seg.text}"

        silence_gap = seg_start - last_end
        too_big = cur_chars + len(line) > max_chars
        natural_break = (
            cur_chars >= target_chars
            and silence_gap >= silence_split_seconds
            and cur_lines
        )

        if too_big or natural_break:
            flush()
            cur_start = seg_start

        cur_lines.append(line)
        cur_ids.append(i)
        cur_chars += len(line)
        cur_end = seg_end
        cur_speakers.add(seg.speaker)
        last_end = seg_end

    flush()
    return chunks
