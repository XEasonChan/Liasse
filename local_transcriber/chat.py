from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional


OLLAMA_ENDPOINT = "http://127.0.0.1:11434"


SUMMARY_PROMPT = """/no_think
你是严谨的学术访谈研究助理。请根据下面这段逐字稿，写一份精炼的访谈总结。

要求：
- 输出中文 Markdown
- 包含「访谈概览」「关键主题」「重要观点 / 引述」「值得跟进的问题」四个 `##` 段
- 区分受访者观点和研究者追问
- 不引入逐字稿之外的信息
- 整体 600-1200 字
- 直接输出结果，不要写思考过程

逐字稿：
{transcript}
"""


def segments_to_text(segments: Iterable[Dict[str, Any]],
                     speaker_labels: Optional[Dict[str, str]] = None,
                     overrides: Optional[Dict[str, str]] = None) -> str:
    speaker_labels = speaker_labels or {}
    overrides = overrides or {}
    lines: List[str] = []
    for seg in segments:
        spk = speaker_labels.get(seg.get("speaker", "")) or seg.get("speaker", "SPEAKER_00")
        text = overrides.get(seg.get("id", ""), seg.get("text", ""))
        start = seg.get("start")
        end = seg.get("end")
        ts = ""
        if start is not None:
            ts = f"[{_clock(start)}-{_clock(end)}] "
        lines.append(f"{ts}{spk}: {text}")
    return "\n".join(lines)


def generate_summary(transcript: str, model: str = "qwen3:4b") -> str:
    prompt = SUMMARY_PROMPT.format(transcript=_trim_for_context(transcript))
    return _generate(prompt, model=model)


def _clock(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--"
    s = int(round(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def _trim_for_context(transcript: str, max_chars: int = 28000) -> str:
    if len(transcript) <= max_chars:
        return transcript
    head = transcript[: max_chars // 2]
    tail = transcript[-max_chars // 2 :]
    return head + "\n\n[...中段省略以适配上下文...]\n\n" + tail


def _generate(prompt: str, model: str, num_ctx: int = 16384, temperature: float = 0.3) -> str:
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": num_ctx},
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_ENDPOINT}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError("无法连接本地 Ollama。请确认服务已启动。") from exc
    return str(data.get("response", "")).strip()
