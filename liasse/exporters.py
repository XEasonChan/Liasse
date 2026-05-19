from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from .models import SpeakerTurn, SummaryResult, TranscriptSegment
from .timefmt import format_clock, format_srt_time


def export_markdown(
    path: Path,
    audio_path: Path,
    segments: Iterable[TranscriptSegment],
    speaker_turns: Iterable[SpeakerTurn],
    summary: Optional[SummaryResult],
) -> None:
    segment_list = list(segments)
    turn_list = list(speaker_turns)
    lines: List[str] = [
        f"# {audio_path.stem} 转录",
        "",
        f"- 音频文件：`{audio_path}`",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 分段数：{len(segment_list)}",
        f"- 说话人片段数：{len(turn_list)}",
        "",
    ]

    if summary:
        lines.extend(["## 本地摘要", "", summary.text.strip(), ""])
        if summary.chunks:
            lines.extend(["## 分块摘要", ""])
            for index, chunk in enumerate(summary.chunks, start=1):
                lines.extend([f"### 分块 {index}", "", chunk.strip(), ""])

    lines.extend(["## 逐字稿", ""])
    for segment in segment_list:
        lines.append(
            f"**{segment.speaker}** "
            f"`{format_clock(segment.start)}-{format_clock(segment.end)}`  "
        )
        lines.append(segment.text.strip())
        lines.append("")

    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def export_json(
    path: Path,
    audio_path: Path,
    segments: Iterable[TranscriptSegment],
    speaker_turns: Iterable[SpeakerTurn],
    summary: Optional[SummaryResult],
) -> None:
    data = {
        "audio_path": str(audio_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "segments": [segment.to_dict() for segment in segments],
        "speaker_turns": [turn.to_dict() for turn in speaker_turns],
        "summary": summary.to_dict() if summary else None,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def export_srt(path: Path, segments: Iterable[TranscriptSegment]) -> None:
    blocks: List[str] = []
    for index, segment in enumerate(segments, start=1):
        if segment.start is None or segment.end is None:
            continue
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_time(segment.start)} --> {format_srt_time(segment.end)}",
                    f"{segment.speaker}: {segment.text.strip()}",
                ]
            )
        )
    path.write_text("\n\n".join(blocks).strip() + "\n", encoding="utf-8")
