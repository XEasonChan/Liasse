from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .models import TranscriptSegment

OLLAMA_ENDPOINT = "http://127.0.0.1:11434"

MAX_SEGMENTS_PER_CHUNK = 80
MAX_CHARS_PER_CHUNK = 12000


class SpeakerLabelingError(RuntimeError):
    pass


@dataclass
class SpeakerLabelingResult:
    segments: List[TranscriptSegment]
    speaker_labels: Dict[str, str]


def label_segments(
    segments: Sequence[TranscriptSegment],
    *,
    model: str = "qwen3:4b",
    num_speakers: Optional[int] = 2,
) -> SpeakerLabelingResult:
    source_segments = list(segments)
    if not source_segments:
        return SpeakerLabelingResult(segments=[], speaker_labels={})

    speaker_count = _speaker_count(num_speakers)
    allowed = [f"SPEAKER_{i:02d}" for i in range(speaker_count)]

    # 单说话人短路：调 LLM 没意义（任务唯一解），还经常返回空 JSON 导致整个
    # 流程报「智能分离失败」。直接给所有片段贴 SPEAKER_00。
    if speaker_count <= 1:
        single = allowed[0]
        labeled = [
            TranscriptSegment(
                start=segment.start,
                end=segment.end,
                text=segment.text,
                speaker=single,
                confidence=segment.confidence,
                source=segment.source,
            )
            for segment in source_segments
        ]
        return SpeakerLabelingResult(
            segments=labeled,
            speaker_labels={single: _default_label(single)},
        )

    assignments: Dict[int, str] = {}

    for chunk in _chunks(source_segments):
        prompt = _build_prompt(chunk, allowed)
        raw = _generate(prompt, model=model)
        for item in _parse_assignments(raw):
            index = _segment_index(item.get("id"))
            if index is None or index < 0 or index >= len(source_segments):
                continue
            speaker = _normalize_speaker(item.get("speaker"), allowed)
            if speaker is not None:
                assignments[index] = speaker

    if not assignments:
        raise SpeakerLabelingError("本地 LLM 没有返回可用的发言人标注。")

    labeled: List[TranscriptSegment] = []
    fallback = allowed[0]
    for index, segment in enumerate(source_segments):
        labeled.append(
            TranscriptSegment(
                start=segment.start,
                end=segment.end,
                text=segment.text,
                speaker=assignments.get(index, fallback),
                confidence=segment.confidence,
                source=segment.source,
            )
        )

    used = {segment.speaker for segment in labeled}
    labels = {
        speaker: _default_label(speaker)
        for speaker in allowed
        if speaker in used or speaker in {"SPEAKER_00", "SPEAKER_01"}
    }
    return SpeakerLabelingResult(segments=labeled, speaker_labels=labels)


def _speaker_count(num_speakers: Optional[int]) -> int:
    if num_speakers is None:
        return 2
    try:
        value = int(num_speakers)
    except (TypeError, ValueError):
        return 2
    return max(1, min(5, value))


def _chunks(segments: Sequence[TranscriptSegment]) -> Iterable[List[Tuple[int, TranscriptSegment]]]:
    current: List[Tuple[int, TranscriptSegment]] = []
    current_chars = 0
    for index, segment in enumerate(segments):
        text = segment.text or ""
        item_chars = len(text) + 80
        if current and (
            len(current) >= MAX_SEGMENTS_PER_CHUNK
            or current_chars + item_chars > MAX_CHARS_PER_CHUNK
        ):
            yield current
            current = []
            current_chars = 0
        current.append((index, segment))
        current_chars += item_chars
    if current:
        yield current


def _build_prompt(chunk: List[Tuple[int, TranscriptSegment]], allowed: Sequence[str]) -> str:
    payload = [
        {
            "id": f"seg-{index}",
            "time": _time_range(segment),
            "text": segment.text,
        }
        for index, segment in chunk
    ]
    allowed_text = ", ".join(allowed)
    role_hint = (
        "SPEAKER_00 通常是采访者/研究者/提问者；"
        "SPEAKER_01 通常是主要受访者；"
        "如果还有其他持续发言的人，再使用后续编号。"
    )
    return f"""/no_think
你是访谈逐字稿的发言人语义标注器。你只能根据文本内容、问答结构、称呼和上下文判断角色；
不要声称自己能听出音色，也不要编造人名。

请为每个片段选择一个 speaker，只能从这些值中选择：{allowed_text}。
角色约定：{role_hint}

严格只输出 JSON 数组，不要 Markdown，不要解释。格式：
[{{"id":"seg-0","speaker":"SPEAKER_00"}}]

片段：
{json.dumps(payload, ensure_ascii=False)}
"""


def _time_range(segment: TranscriptSegment) -> str:
    return f"{_clock(segment.start)}-{_clock(segment.end)}"


def _clock(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--"
    total = int(round(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def _parse_assignments(text: str) -> List[Dict[str, Any]]:
    json_text = _extract_json_array(text)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise SpeakerLabelingError("本地 LLM 返回的发言人 JSON 无法解析。") from exc
    if not isinstance(data, list):
        raise SpeakerLabelingError("本地 LLM 返回的发言人标注不是数组。")
    return [item for item in data if isinstance(item, dict)]


def _extract_json_array(text: str) -> str:
    raw = (text or "").strip()
    if "```" in raw:
        match = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.S | re.I)
        if match:
            raw = match.group(1).strip()

    start = raw.find("[")
    if start == -1:
        raise SpeakerLabelingError("本地 LLM 没有返回 JSON 数组。")
    depth = 0
    for pos in range(start, len(raw)):
        if raw[pos] == "[":
            depth += 1
        elif raw[pos] == "]":
            depth -= 1
            if depth == 0:
                return raw[start : pos + 1]
    raise SpeakerLabelingError("本地 LLM 返回的 JSON 数组不完整。")


def _segment_index(raw_id: Any) -> Optional[int]:
    match = re.search(r"(\d+)", str(raw_id or ""))
    if not match:
        return None
    return int(match.group(1))


def _normalize_speaker(raw: Any, allowed: Sequence[str]) -> Optional[str]:
    value = str(raw or "").strip()
    upper = value.upper()
    if upper in allowed:
        return upper
    match = re.search(r"(\d+)", upper)
    if match:
        candidate = f"SPEAKER_{int(match.group(1)):02d}"
        if candidate in allowed:
            return candidate

    role_map = {
        "采访者": "SPEAKER_00",
        "主持人": "SPEAKER_00",
        "研究者": "SPEAKER_00",
        "提问者": "SPEAKER_00",
        "interviewer": "SPEAKER_00",
        "受访者": "SPEAKER_01",
        "嘉宾": "SPEAKER_01",
        "回答者": "SPEAKER_01",
        "interviewee": "SPEAKER_01",
    }
    lowered = value.lower()
    for key, speaker in role_map.items():
        if key in value or key in lowered:
            return speaker if speaker in allowed else None
    return None


def _default_label(speaker: str) -> str:
    mapping = {
        "SPEAKER_00": "采访者",
        "SPEAKER_01": "受访者",
        "SPEAKER_02": "参与者 3",
        "SPEAKER_03": "参与者 4",
        "SPEAKER_04": "参与者 5",
    }
    return mapping.get(speaker, speaker)


def _generate(prompt: str, *, model: str) -> str:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_ctx": 16384},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_ENDPOINT}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
            request, timeout=600
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise SpeakerLabelingError("无法连接本地 Ollama，智能分离已跳过。") from exc
    except json.JSONDecodeError as exc:
        raise SpeakerLabelingError("Ollama 返回内容无法解析，智能分离已跳过。") from exc
    return str(data.get("response") or "")

