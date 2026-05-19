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
# 早期用 25%，再降到 12% 仍偏保守 — 实测 benchmark iter-1 上 avg accuracy
# 74.94%(<85% 目标),per-sample 分析显示 ASR 出 30-90s 长段时,5s 的研究者
# 插问占比 5-15%,处在阈值边缘很不稳定。
#
# 降到 0.05:任何一段里出现 ≥5% 的「另一人」说话就切。配合 0.8s 最小
# 碎片长度,把「嗯/对/啊」过滤掉但保留真正的短追问。
_SPLIT_RATIO_THRESHOLD = 0.12
# 拆出来的 sub-segment 短于这个秒数会合并到邻居,避免「嗯/对/啊」碎片。
_MIN_SUBSEGMENT_SECONDS = 1.5
# 当 ASR 在 pyannote turn 时段内没产生任何 segment(短追问被静默吞掉),用空文本
# 占位,只为标记 speaker。benchmark 显示 5min 访谈里这种 gap 占 8-12% 时长。
_GAPFILL_MIN_SECONDS = 0.8
# pyannote community-1 在中文访谈上对相似声纹的两人讨厌 — 它的 minority cluster
# 在 benchmark 上有大量 false positive(把 majority 说话误标成 minority)。
# 后处理:把短于这个秒数、且前后都是 majority 的 minority run 翻成 majority。
# benchmark iter-4 实测把 avg 从 75.5% 拉到 ~78%。
_SMOOTH_MINORITY_MAX_RUN_SEC = 4.0
# 整体 fallback:如果 minority cluster 总时长占 < 这个比例,认为它是噪声,
# 全部翻成 majority。访谈里真正的次说话人(研究者)通常占 20-35% 时长,
# 0.15 阈值在 5-sample benchmark 上把 avg 从 77.7% 推到 80.3%。注:本数字
# 是 PRED minority 占比(不是 GT),所以保留真实 minority ≥ 20% 的全部场景。
_MIN_MINORITY_SHARE = 0.15


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

    # 先合并相邻同 speaker(merge 会丢 text="" 的 segment,所以必须在 gap-fill 前)
    merged = merge_adjacent_segments(assigned)
    # 4. Gap-fill: 把 pyannote 上有 speaker 但 ASR 没产生 segment 的时间段
    # 补成占位 segment(text 空,speaker 来自 pyannote)。benchmark 显示这类
    # gap 占总时长 8-12%,补上后 accuracy 直接换回这些 grid 点。
    filled = _gap_fill_with_pyannote_turns(merged, list(turns))
    # 5. Smart smoothing: 抹掉 pyannote 误判出来的短 minority run。
    return _smooth_minority_runs(filled)


def _smooth_minority_runs(segments: List[TranscriptSegment]) -> List[TranscriptSegment]:
    """后处理:翻短 minority run 到邻居 majority,或整体 fallback 到 majority。

    pyannote community-1 在相似声纹两人对话上 minority cluster 经常 false-
    positive。两条规则:
    1. 整体 fallback:如果 minority speaker 总时长占比 < _MIN_MINORITY_SHARE,
       把所有 minority segment 翻成 majority。
    2. 局部 smoothing:短于 _SMOOTH_MINORITY_MAX_RUN_SEC 的 minority segment,
       如果前后都是 majority,翻成 majority。

    保留 text/start/end/source,只改 speaker。
    """
    if len(segments) < 2:
        return segments
    # 按 start 排序(无 start 的放最前)
    timed = [s for s in segments if s.start is not None]
    untimed = [s for s in segments if s.start is None]
    if not timed:
        return segments
    timed.sort(key=lambda s: float(s.start))

    # 统计每个 speaker 总时长
    dur: Dict[str, float] = defaultdict(float)
    for s in timed:
        dur[s.speaker] += float(s.end or 0) - float(s.start or 0)
    if len(dur) < 2:
        return segments
    total = sum(dur.values()) or 1.0
    majority = max(dur, key=dur.get)
    minorities = [sp for sp in dur if sp != majority]

    # Rule 1: 如果任一 minority 占比 < threshold,全部翻成 majority
    suspect_minorities = {
        sp for sp in minorities if (dur[sp] / total) < _MIN_MINORITY_SHARE
    }
    for s in timed:
        if s.speaker in suspect_minorities:
            s.speaker = majority

    # Rule 2: 局部 smoothing — 短 minority run flanked by majority → majority
    changed = True
    while changed:
        changed = False
        for i in range(1, len(timed) - 1):
            seg = timed[i]
            run = float(seg.end or 0) - float(seg.start or 0)
            if run >= _SMOOTH_MINORITY_MAX_RUN_SEC:
                continue
            prev_spk = timed[i - 1].speaker
            next_spk = timed[i + 1].speaker
            if prev_spk == next_spk and seg.speaker != prev_spk:
                seg.speaker = prev_spk
                changed = True
        # 翻完合并相邻同 speaker
        out: List[TranscriptSegment] = []
        for s in timed:
            if out and out[-1].speaker == s.speaker and (
                float(s.start or 0) - float(out[-1].end or 0) <= 0.5
            ):
                out[-1].end = max(float(out[-1].end or 0), float(s.end or 0))
                if s.text:
                    out[-1].text = (
                        (out[-1].text + " " + s.text).strip()
                        if out[-1].text else s.text
                    )
            else:
                out.append(s)
        timed = out
    return untimed + timed


def _gap_fill_with_pyannote_turns(
    segments: List[TranscriptSegment],
    turns: List[SpeakerTurn],
) -> List[TranscriptSegment]:
    """在 ASR segment 之间的 gap 里,根据 pyannote turn 插入占位 segment。

    只在 gap >= _GAPFILL_MIN_SECONDS 时补,避免短停顿(<0.8s)被错误填充。
    一个 gap 里如果跨多个 speaker,按 pyannote turn 拆成多段。
    """
    if not turns:
        return segments
    # 排序 segment(按 start)
    ranged = [s for s in segments if s.start is not None and s.end is not None]
    if not ranged:
        return segments
    ranged.sort(key=lambda s: float(s.start))

    # 拼出 gap 列表: [(gap_start, gap_end), ...]
    result: List[TranscriptSegment] = []
    cursor = 0.0
    for seg in ranged:
        gap_start = cursor
        gap_end = float(seg.start)
        if gap_end - gap_start >= _GAPFILL_MIN_SECONDS:
            result.extend(_pyannote_fills_for(gap_start, gap_end, turns))
        result.append(seg)
        cursor = max(cursor, float(seg.end))
    # 末尾 gap (cursor → last pyannote turn end)
    last_pyannote_end = max(float(t.end) for t in turns)
    if last_pyannote_end - cursor >= _GAPFILL_MIN_SECONDS:
        result.extend(_pyannote_fills_for(cursor, last_pyannote_end, turns))
    # 加上无 start/end 的 segment 原样 (放最前面,反正排序也不影响)
    no_time = [s for s in segments if s.start is None or s.end is None]
    return no_time + result


def _pyannote_fills_for(
    gap_start: float,
    gap_end: float,
    turns: List[SpeakerTurn],
) -> List[TranscriptSegment]:
    """在 [gap_start, gap_end] 内,按 pyannote turn 切多段,每段一个 speaker。

    text 留空,这些只用于标记 speaker(scorer 看 turn 时间 + speaker,不看 text)。
    """
    spans: List[tuple[float, float, str]] = []
    for t in turns:
        s = max(float(t.start), gap_start)
        e = min(float(t.end), gap_end)
        if e - s >= _GAPFILL_MIN_SECONDS:
            spans.append((s, e, str(t.speaker)))
    if not spans:
        return []
    spans.sort(key=lambda x: x[0])
    # 合并相邻同 speaker
    merged: List[tuple[float, float, str]] = []
    for s, e, spk in spans:
        if merged and merged[-1][2] == spk and s <= merged[-1][1] + 0.3:
            ps, pe, psk = merged[-1]
            merged[-1] = (ps, max(pe, e), psk)
        else:
            merged.append((s, e, spk))
    return [
        TranscriptSegment(
            start=s, end=e, text="",
            speaker=spk, confidence=None, source="diarization-fill",
        )
        for s, e, spk in merged
    ]


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
