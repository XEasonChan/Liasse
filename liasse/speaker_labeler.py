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
    """v0.2.4 起改为 **cluster-mapping** 模式。

    pyannote 已经按声纹把 segment 分好簇（SPEAKER_00 / 01 / ...）。
    这里 LLM 的工作不是「per-segment 重分类」（会覆盖 pyannote 的声学判断），
    而是「per-cluster 贴角色标签」：

        输入  segments[speaker]:  [SPEAKER_00, SPEAKER_00, SPEAKER_01, ...]   (来自 pyannote)
        LLM 看每簇的代表性文本样本
        输出  speaker_labels:    {SPEAKER_00: "采访者", SPEAKER_01: "受访者"}

    segments 的 speaker 字段**保持不变**，永远是 pyannote 的输出。
    """
    source_segments = list(segments)
    if not source_segments:
        return SpeakerLabelingResult(segments=[], speaker_labels={})

    speaker_count = _speaker_count(num_speakers)

    # 按 pyannote 的 speaker 字段分簇
    cluster_texts: Dict[str, List[str]] = {}
    for seg in source_segments:
        spk = seg.speaker or "SPEAKER_00"
        if seg.text:
            cluster_texts.setdefault(spk, []).append(seg.text)
        else:
            cluster_texts.setdefault(spk, [])

    present_clusters = sorted(cluster_texts.keys())

    # 单簇短路：调 LLM 没意义（唯一解），过去会返回空 JSON 触发
    # SpeakerLabelingError → UI 弹「智能分离失败」横幅。
    if len(present_clusters) <= 1 or speaker_count <= 1:
        single = present_clusters[0] if present_clusters else "SPEAKER_00"
        # segments 原样透传（不改 speaker）
        labeled = [
            TranscriptSegment(
                start=s.start, end=s.end, text=s.text,
                speaker=s.speaker or single,
                confidence=s.confidence, source=s.source,
            )
            for s in source_segments
        ]
        return SpeakerLabelingResult(
            segments=labeled,
            speaker_labels={single: _default_label(single)},
        )

    # 多簇 → LLM 只产出 cluster→role 映射，不改 segment.speaker
    prompt = _build_cluster_mapping_prompt(present_clusters, cluster_texts)
    raw = _generate(prompt, model=model)
    role_mapping = _parse_cluster_mapping(raw, present_clusters)

    if not role_mapping:
        raise SpeakerLabelingError("本地 LLM 没有返回可用的 cluster→role 映射。")

    # 保留 pyannote 的 per-segment speaker，只重建 speaker_labels
    labeled = [
        TranscriptSegment(
            start=s.start, end=s.end, text=s.text,
            speaker=s.speaker or present_clusters[0],
            confidence=s.confidence, source=s.source,
        )
        for s in source_segments
    ]
    # role_mapping 里没覆盖到的簇 fallback 到默认标签
    speaker_labels = {
        cluster: role_mapping.get(cluster, _default_label(cluster))
        for cluster in present_clusters
    }
    return SpeakerLabelingResult(segments=labeled, speaker_labels=speaker_labels)


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


def _build_cluster_mapping_prompt(
    clusters: Sequence[str], cluster_texts: Dict[str, List[str]]
) -> str:
    """v0.2.4 新 prompt：给 LLM 看 pyannote 已经分好的簇的代表性文本，
    要 LLM 输出 cluster→角色 的 JSON 映射，**不让 LLM 重新分类 segment**。
    每簇拼接前 ~600 字符样本（避免上下文爆炸）。"""
    SAMPLE_CHARS = 600
    sample_lines: List[str] = []
    for cluster in clusters:
        joined = " ".join(cluster_texts.get(cluster, []))
        if len(joined) > SAMPLE_CHARS:
            head = joined[: SAMPLE_CHARS // 2]
            tail = joined[-SAMPLE_CHARS // 2:]
            joined = f"{head} … {tail}"
        sample_lines.append(f"{cluster}:\n  \"{joined}\"")
    samples_block = "\n\n".join(sample_lines)

    cluster_list = ", ".join(clusters)
    return f"""你是访谈逐字稿的角色标签器。下面是 pyannote 已经按声纹分好的若干簇 \
({cluster_list})，每簇有代表性文本样本。请只根据文本判断每个簇对应什么角色。

允许的角色：采访者、受访者、参与者 3、参与者 4、参与者 5。
约定：采访者通常提问、引导话题；受访者通常回答问题、讲述细节；其余持续发言者用「参与者 N」。

严格只输出 JSON 对象，不要 Markdown，不要解释，键是簇 ID，值是角色：
{{"SPEAKER_00":"采访者","SPEAKER_01":"受访者"}}

簇样本：
{samples_block}
"""


def _parse_cluster_mapping(
    text: str, allowed_clusters: Sequence[str]
) -> Dict[str, str]:
    """解析 LLM 返回的 {cluster_id → role_label} JSON。
    宽松：忽略未知簇 ID；role 中文/英文都接受；JSON 嵌在 Markdown / 解释里也能挖出来。"""
    raw = (text or "").strip()
    if "```" in raw:
        match = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.S | re.I)
        if match:
            raw = match.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        obj = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(obj, dict):
        return {}

    allowed_set = set(allowed_clusters)
    role_normalize = {
        "采访者": "采访者", "主持人": "采访者", "研究者": "采访者", "提问者": "采访者",
        "interviewer": "采访者", "host": "采访者",
        "受访者": "受访者", "嘉宾": "受访者", "回答者": "受访者",
        "interviewee": "受访者", "guest": "受访者",
    }

    out: Dict[str, str] = {}
    for k, v in obj.items():
        cluster = str(k).strip().upper()
        if cluster not in allowed_set:
            # LLM 可能写 SPEAKER0 / speaker_00 之类，标准化一下
            m = re.search(r"(\d+)", cluster)
            if m:
                candidate = f"SPEAKER_{int(m.group(1)):02d}"
                if candidate in allowed_set:
                    cluster = candidate
        if cluster not in allowed_set:
            continue
        value = str(v or "").strip()
        lowered = value.lower()
        role = None
        for key, label in role_normalize.items():
            if key in value or key in lowered:
                role = label
                break
        if role is None and value:
            # 保留原始（比如「参与者 3」之类）
            role = value
        if role:
            out[cluster] = role
    return out


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
    # Qwen3 是 hybrid thinking 模型；prompt 里 /no_think directive 不一定被
    # 遵守，必须显式 think=False 才能彻底关掉 thinking token。否则一个简单
    # 的 speaker JSON 推理也会跑 100+ 秒（绝大多数耗时全在 think tokens 里）。
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "keep_alive": "30m",
            "options": {
                "temperature": 0.0,
                "num_ctx": 4096,
                "num_predict": 1024,
            },
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

