"""逐段翻译引擎 — Ollama qwen3:4b + 词库注入。

公共 API:
- build_translate_prompt(segments, target, glossary) -> str: 构造 prompt
- translate_segments(segments, target, glossary, ollama, model, batch_size)
  -> list[TranslatedSegment]: 分批调 Ollama,返回每段译文

不接云 API,符合 IRB 离线约束。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional

from .ollama_lifecycle import OllamaClient
from .schemas import Glossary, TranslatedSegment

LANG_DIRECTIVE = {
    "Chinese": "翻译成自然的简体中文",
    "English": "translate into natural English",
    "Cantonese": "翻译成口语化的香港粤语",
    "Spanish": "translate into natural Spanish",
}


def build_translate_prompt(
    segments: List[dict],
    target: str,
    glossary: Optional[Glossary],
) -> str:
    """构造 prompt。结构:
      <prefix /no_think>
      <directive>
      <rules>
      <glossary (if any)>
      <INPUT JSON list>
      <OUTPUT schema>
    """
    directive = LANG_DIRECTIVE.get(target, f"translate into {target}")
    parts: list[str] = [
        "/no_think",
        f"You are a professional interview transcript translator. {directive}.",
        "RULES:",
        "1. Preserve speaker tone and pacing markers (e.g. 「嗯」, 「我覺得」, 'um', 'I mean').",
        "2. Keep proper nouns, brand names, and code identifiers unchanged unless glossary says otherwise.",
        "3. Do NOT merge or split segments. One input segment -> exactly one output translation, by id.",
        "4. Return STRICT JSON only. No prose before or after, no markdown code fence.",
    ]
    if glossary and glossary.entries:
        parts.append("")
        parts.append("Glossary — these terms MUST use the listed translation verbatim:")
        for e in glossary.entries:
            line = f"- {e.source} -> {e.target}"
            if e.domain:
                line += f"  ({e.domain})"
            parts.append(line)
    parts.append("")
    parts.append("INPUT segments (JSON list of {id, speaker, text}):")
    parts.append(json.dumps(
        [{"id": s["id"], "speaker": s.get("speaker"), "text": s["text"]} for s in segments],
        ensure_ascii=False,
    ))
    parts.append("")
    parts.append(
        'OUTPUT shape: {"translations": [{"id": <int>, "translation": <str>}, ...]} '
        '— translations array length MUST equal input length, ids MUST match input ids.'
    )
    return "\n".join(parts)


_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def _parse_translation_response(raw: str) -> dict:
    """Qwen 偶尔在 JSON 前后多嘴 ("Here is the JSON:") 或带 ```json fence;
    抓最外层 {...} 兜底。失败抛 ValueError,不静默吞。
    """
    raw = raw.strip()
    m = _JSON_BLOCK_RE.search(raw)
    if not m:
        raise ValueError(f"无法解析翻译输出 (无 JSON 块):{raw[:200]}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"无法解析翻译输出 (JSON 错误:{exc}):{raw[:200]}") from exc


def _coerce_segment(s: Any) -> dict:
    """支持 dict 或 dataclass-ish object (有 .start/.end/.speaker/.text/.id 属性)。"""
    if isinstance(s, dict):
        return s
    out = {}
    for k in ("id", "start", "end", "speaker", "text"):
        if hasattr(s, k):
            out[k] = getattr(s, k)
    return out


def translate_segments(
    segments: Iterable[Any],
    target: str,
    glossary: Optional[Glossary],
    ollama: OllamaClient,
    model: str = "qwen3:4b",
    batch_size: int = 20,
) -> List[TranslatedSegment]:
    """逐批调 Ollama 翻译。

    - 输入 segments 可以是 dict 或带属性的对象。
    - 每段必须有 id (int 或可转 int);没有则按位置序号补 1..N。
    - batch_size 控制单次 prompt 包含几段,过大易超 num_ctx 或被模型偷懒。
    """
    seg_list: list[dict] = []
    for i, raw in enumerate(segments, start=1):
        s = _coerce_segment(raw)
        if "id" not in s or s.get("id") is None:
            s = {**s, "id": i}
        else:
            try:
                s["id"] = int(s["id"])
            except (TypeError, ValueError):
                s["id"] = i
        seg_list.append(s)
    if not seg_list:
        return []

    results: List[TranslatedSegment] = []
    for i in range(0, len(seg_list), batch_size):
        batch = seg_list[i:i + batch_size]
        prompt = build_translate_prompt(batch, target, glossary)
        raw = ollama.generate(model=model, prompt=prompt, temperature=0.2)
        parsed = _parse_translation_response(raw)
        translations = {
            int(t["id"]): str(t.get("translation", ""))
            for t in parsed.get("translations", [])
            if "id" in t
        }
        for s in batch:
            results.append(TranslatedSegment(
                id=int(s["id"]),
                start=s.get("start"),
                end=s.get("end"),
                speaker=s.get("speaker"),
                text=str(s["text"]),
                translation=translations.get(int(s["id"]), ""),
            ))
    return results


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
