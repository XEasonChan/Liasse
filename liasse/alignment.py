from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional

from .models import SpeakerTurn, TranscriptSegment


def overlap_seconds(
    first_start: Optional[float],
    first_end: Optional[float],
    second_start: float,
    second_end: float,
) -> float:
    if first_start is None or first_end is None:
        return 0.0
    return max(0.0, min(first_end, second_end) - max(first_start, second_start))


# 把跨 speaker 的长 ASR segment 拆成 sub-segment 的阈值。如果 secondary
# speaker 累计 overlap 占 segment 总时长的 >= 这个比例，就按 pyannote turn
# 边界拆。
#
# 访谈里典型场景：受访者长答 + 研究者短追问。研究者插话通常 5-15% 时长。
# 早期用 25%，但实测真实样本里 95% 的「受访者主体段」minority < 16%，
# 几乎从不触发拆分 → 还是显示全是 SPEAKER_00。
#
# 降到 12%：让一段里出现一次明显的追问就会被切出来。配合
# _MIN_SUBSEGMENT_SECONDS=1.5 自动过滤 <1.5s 的「嗯/对」碎片，不会因为
# 降阈值而被噪声污染。
_SPLIT_RATIO_THRESHOLD = 0.12
# 拆出来的 sub-segment 短于这个秒数会合并到邻居，避免「嗯/对/啊」碎片。
_MIN_SUBSEGMENT_SECONDS = 1.5


def assign_speakers(
    segments: Iterable[TranscriptSegment],
    speaker_turns: Iterable[SpeakerTurn],
) -> List[TranscriptSegment]:
    """给每个 ASR segment 赋 speaker。

    两种策略组合：
    1. 单 speaker segment（或 minority 占比 < 25%）：按累计 overlap 选
       majority speaker，segment 不切。
    2. 跨 speaker segment（minority ≥ 25%）：按 pyannote turn 边界把
       segment 拆成多个 sub-segment，每个 sub-segment 单独赋 speaker，
       text 按时间比例切字符。

    历史 bug：旧实现选「单个 overlap 最长的 turn」。pyannote 输出几十个
    细 turn (0.3-5s)，ASR segment 30-90s 长。访谈里受访者 turns 个个都
    比研究者短追问长，导致每个长 segment 都被赋受访者，所有 segment 看
    起来都是同一人。

    新实现下，70 秒长的「受访者答 + 研究者插问 + 受访者继续答」segment
    会被拆成 3 段，前端看到正确的对话往复。
    """
    turns = list(speaker_turns)
    assigned: List[TranscriptSegment] = []

    for segment in segments:
        if segment.start is None or segment.end is None:
            assigned.append(segment)
            continue

        seg_duration = float(segment.end) - float(segment.start)
        if seg_duration <= 0:
            assigned.append(segment)
            continue

        # 1. 累计每个 speaker 在 segment 内的 overlap
        by_speaker: Dict[str, float] = defaultdict(float)
        first_seen: Dict[str, float] = {}
        for turn in turns:
            amount = overlap_seconds(segment.start, segment.end,
                                      turn.start, turn.end)
            if amount > 0:
                by_speaker[turn.speaker] += amount
                if turn.speaker not in first_seen:
                    first_seen[turn.speaker] = turn.start

        if not by_speaker:
            assigned.append(segment)
            continue

        # 2. 决定是否需要拆
        majority = max(by_speaker.items(),
                       key=lambda kv: (kv[1], -first_seen.get(kv[0], 0.0)))
        majority_speaker = majority[0]
        minority_total = sum(v for k, v in by_speaker.items()
                             if k != majority_speaker)
        minority_ratio = minority_total / seg_duration

        if len(by_speaker) == 1 or minority_ratio < _SPLIT_RATIO_THRESHOLD:
            # 单 speaker 或 minority 太少：保留原 segment
            segment.speaker = majority_speaker
            assigned.append(segment)
            continue

        # 3. 拆：按 pyannote turn 边界切 sub-segment
        sub_segments = _split_segment_by_turns(segment, turns)
        if not sub_segments:
            segment.speaker = majority_speaker
            assigned.append(segment)
        else:
            assigned.extend(sub_segments)

    return merge_adjacent_segments(assigned)


def _split_segment_by_turns(
    segment: TranscriptSegment,
    turns: List[SpeakerTurn],
) -> List[TranscriptSegment]:
    """把一个 segment 按 pyannote turn 边界拆成 N 个 sub-segment。

    text 没有词级时间戳，所以按时间比例切字符（中文每个字独立，效果尚可；
    英文可能切到单词中间，访谈场景多为中文所以接受）。

    short sub-segment (<1.5s) 会合并到相邻的 majority sub-segment，避免
    「嗯/对/啊」之类的碎片污染逐字稿。
    """
    seg_start = float(segment.start)
    seg_end = float(segment.end)
    seg_duration = seg_end - seg_start

    # 收集所有与 segment 重叠的 turn，clip 到 segment 边界
    spans: List[tuple[float, float, str]] = []
    for turn in turns:
        s = max(turn.start, seg_start)
        e = min(turn.end, seg_end)
        if e > s:
            spans.append((s, e, turn.speaker))
    if not spans:
        return []

    spans.sort(key=lambda x: x[0])

    # 合并相邻同 speaker：连续 spans 同 speaker 视为一段
    merged_spans: List[tuple[float, float, str]] = []
    for s, e, spk in spans:
        if merged_spans and merged_spans[-1][2] == spk and s <= merged_spans[-1][1] + 0.5:
            # 与上一段同 speaker 且几乎相连，合并
            prev_s, prev_e, prev_spk = merged_spans[-1]
            merged_spans[-1] = (prev_s, max(prev_e, e), prev_spk)
        else:
            merged_spans.append((s, e, spk))

    # 短碎片合并到相邻 majority
    cleaned: List[tuple[float, float, str]] = []
    for span in merged_spans:
        s, e, spk = span
        dur = e - s
        if dur < _MIN_SUBSEGMENT_SECONDS and cleaned:
            # 合并到前一个
            prev_s, prev_e, prev_spk = cleaned[-1]
            cleaned[-1] = (prev_s, e, prev_spk)
        else:
            cleaned.append(span)

    # 同上再扫一遍处理首段短的情况
    if cleaned and (cleaned[0][1] - cleaned[0][0]) < _MIN_SUBSEGMENT_SECONDS and len(cleaned) > 1:
        first_s, first_e, _ = cleaned[0]
        second_s, second_e, second_spk = cleaned[1]
        cleaned[1] = (first_s, second_e, second_spk)
        cleaned = cleaned[1:]

    if len(cleaned) <= 1:
        # 拆完只剩一段，退回不拆
        return []

    # 4. 按时间比例切 text
    text = segment.text or ""
    total_chars = len(text)
    result: List[TranscriptSegment] = []
    char_cursor = 0
    for i, (s, e, spk) in enumerate(cleaned):
        is_last = i == len(cleaned) - 1
        if is_last:
            sub_text = text[char_cursor:]
        else:
            ratio = (e - s) / seg_duration if seg_duration > 0 else 0
            n_chars = max(1, int(round(total_chars * ratio)))
            end_idx = min(char_cursor + n_chars, total_chars)
            sub_text = text[char_cursor:end_idx]
            char_cursor = end_idx
        if not sub_text.strip():
            continue
        result.append(TranscriptSegment(
            start=s,
            end=e,
            text=sub_text.strip(),
            speaker=spk,
            confidence=segment.confidence,
            source=segment.source,
        ))

    return result


def merge_adjacent_segments(
    segments: Iterable[TranscriptSegment],
    max_gap: float = 1.0,
    max_chars: int = 360,
) -> List[TranscriptSegment]:
    merged: List[TranscriptSegment] = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        current = TranscriptSegment(
            start=segment.start,
            end=segment.end,
            text=text,
            speaker=segment.speaker,
            confidence=segment.confidence,
            source=segment.source,
        )
        if not merged:
            merged.append(current)
            continue

        previous = merged[-1]
        same_speaker = previous.speaker == current.speaker
        known_gap = previous.end is not None and current.start is not None
        close_enough = known_gap and (current.start - previous.end) <= max_gap
        short_enough = len(previous.text) + len(current.text) <= max_chars

        if same_speaker and close_enough and short_enough:
            previous.text = f"{previous.text} {current.text}".strip()
            previous.end = current.end
            if previous.confidence is not None and current.confidence is not None:
                previous.confidence = (previous.confidence + current.confidence) / 2
        else:
            merged.append(current)

    return merged
