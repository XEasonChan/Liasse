from __future__ import annotations

from typing import Iterable, List, Optional

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


def assign_speakers(
    segments: Iterable[TranscriptSegment],
    speaker_turns: Iterable[SpeakerTurn],
) -> List[TranscriptSegment]:
    turns = list(speaker_turns)
    assigned: List[TranscriptSegment] = []

    for segment in segments:
        best_turn = None
        best_overlap = 0.0
        for turn in turns:
            amount = overlap_seconds(segment.start, segment.end, turn.start, turn.end)
            if amount > best_overlap:
                best_overlap = amount
                best_turn = turn

        if best_turn is not None and best_overlap > 0:
            segment.speaker = best_turn.speaker
        assigned.append(segment)

    return merge_adjacent_segments(assigned)


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
