from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.request


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


OLLAMA_ENDPOINT = "http://127.0.0.1:11434"


DIGEST_PROMPT = """/no_think
你将看到一段访谈的完整逐字稿。提取以下结构化要点，要简洁、不编造：

1. 访谈基本信息（参与人、估计时长、主题）
2. 关键人物（每个人的角色、立场、知识背景）
3. 主要话题（按出现顺序，每个话题 1-2 句概括）
4. 重要观点与引述（用引号标出关键原话，附说话人）
5. 待跟进的问题（访谈中提到的悬而未决的点）

输出中文 Markdown。每个部分用 `## 标题` 起。整体控制在 1500 字以内。直接输出结果，不要写思考过程。

逐字稿：
{transcript}
"""


CHAT_SYSTEM_PROMPT = """/no_think
你是一个研究助理。下面是用户最近转录的一段访谈的核心要点，所有问答都基于此：

{digest}

下面是按用户问题从逐字稿中本地检索到的相关片段。优先使用这些片段回答；如果片段不足，再参考上面的核心要点：

{retrieval_context}

回答时：
- 如果要点和检索片段里都没有直接答案，明确说"材料中未提及"
- 引用具体观点时附带说话人和大致时间段（如果材料里有）
- 用中文，简洁，避免无关展开
- 直接给答案，不要展示思考过程
"""


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


def segments_to_text(segments: Iterable[Dict[str, Any]], speaker_labels: Optional[Dict[str, str]] = None,
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


def retrieve_context(
    segments: Iterable[Dict[str, Any]],
    query: str,
    speaker_labels: Optional[Dict[str, str]] = None,
    overrides: Optional[Dict[str, str]] = None,
    *,
    top_k: int = 4,
    target_chars: int = 1800,
    max_context_chars: int = 7000,
) -> str:
    """轻量本地 RAG：按关键词从当前访谈逐字稿召回相关时间段。

    这里不用 embedding，避免为离线桌面应用再加载一个模型。中文优先用 jieba，
    不可用时退回字符 bigram + 英文 token。
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return "未检索到与问题直接相关的逐字稿片段。"

    chunks = _segment_chunks(
        list(segments),
        speaker_labels=speaker_labels,
        overrides=overrides,
        target_chars=target_chars,
    )
    if not chunks:
        return "未检索到与问题直接相关的逐字稿片段。"

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for chunk in chunks:
        chunk_tokens = _tokenize(chunk["text"])
        if not chunk_tokens:
            continue
        score = _bm25_lite(query_tokens, chunk_tokens)
        if score > 0:
            scored.append((score, chunk))

    if not scored:
        return "未检索到与问题直接相关的逐字稿片段。"

    scored.sort(key=lambda item: item[0], reverse=True)
    parts: List[str] = []
    used_chars = 0
    for rank, (score, chunk) in enumerate(scored[:top_k], start=1):
        header = (
            f"### 片段 {rank} "
            f"({_clock(chunk.get('start'))}-{_clock(chunk.get('end'))}, score={score:.2f})"
        )
        block = f"{header}\n{chunk['text'].strip()}"
        if used_chars + len(block) > max_context_chars:
            break
        parts.append(block)
        used_chars += len(block)

    return "\n\n".join(parts) if parts else "未检索到与问题直接相关的逐字稿片段。"


def _clock(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--"
    s = int(round(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def _segment_chunks(
    segments: List[Dict[str, Any]],
    speaker_labels: Optional[Dict[str, str]],
    overrides: Optional[Dict[str, str]],
    target_chars: int,
) -> List[Dict[str, Any]]:
    speaker_labels = speaker_labels or {}
    overrides = overrides or {}
    chunks: List[Dict[str, Any]] = []
    current: List[str] = []
    current_start: Optional[float] = None
    current_end: Optional[float] = None

    def flush() -> None:
        nonlocal current, current_start, current_end
        if not current:
            return
        chunks.append({
            "text": "\n".join(current),
            "start": current_start,
            "end": current_end,
        })
        current = []
        current_start = None
        current_end = None

    for seg in segments:
        start = seg.get("start")
        end = seg.get("end")
        speaker = speaker_labels.get(seg.get("speaker", "")) or seg.get("speaker", "SPEAKER_00")
        text = overrides.get(seg.get("id", ""), seg.get("text", ""))
        line = f"[{_clock(start)}-{_clock(end)}] {speaker}: {text}"
        if current and sum(len(item) for item in current) + len(line) > target_chars:
            flush()
        if current_start is None:
            current_start = start
        current_end = end
        current.append(line)

    flush()
    return chunks


def _tokenize(text: str) -> List[str]:
    text = (text or "").strip().lower()
    if not text:
        return []
    tokens: List[str] = []

    try:
        import jieba  # type: ignore

        tokens.extend(t for t in jieba.lcut(text) if len(t.strip()) >= 2)
    except Exception:
        tokens.extend(re.findall(r"[a-z0-9_]{2,}", text))

    tokens.extend(re.findall(r"[a-z0-9_]{2,}", text))
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.extend("".join(pair) for pair in zip(chinese_chars, chinese_chars[1:]))
    return [t for t in tokens if t.strip()]


def _bm25_lite(query_tokens: List[str], doc_tokens: List[str]) -> float:
    counts: Dict[str, int] = {}
    for token in doc_tokens:
        counts[token] = counts.get(token, 0) + 1
    length_norm = 1.0 / math.sqrt(max(len(doc_tokens), 1))
    score = 0.0
    for token in query_tokens:
        tf = counts.get(token, 0)
        if tf:
            score += (1.0 + math.log1p(tf)) * length_norm
    return score


def _trim_for_context(transcript: str, max_chars: int = 28000) -> str:
    if len(transcript) <= max_chars:
        return transcript
    head = transcript[: max_chars // 2]
    tail = transcript[-max_chars // 2 :]
    return head + "\n\n[...中段省略以适配上下文...]\n\n" + tail


def generate_digest(transcript: str, model: str = "qwen3:4b") -> str:
    prompt = DIGEST_PROMPT.format(transcript=_trim_for_context(transcript))
    return _generate(prompt, model=model)


def generate_summary(transcript: str, model: str = "qwen3:4b") -> str:
    prompt = SUMMARY_PROMPT.format(transcript=_trim_for_context(transcript))
    return _generate(prompt, model=model)


def _generate(prompt: str, model: str, num_ctx: int = 16384, temperature: float = 0.3) -> str:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_ENDPOINT}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _opener().open(request, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError("无法连接本地 Ollama。请确认服务已启动。") from exc
    return str(data.get("response", "")).strip()


def stream_chat(
    digest: str,
    history: List[Dict[str, str]],
    message: str,
    model: str = "qwen3:4b",
    retrieval_context: str = "",
) -> Iterator[str]:
    """Yields response text deltas from Ollama /api/chat streaming endpoint."""
    messages: List[Dict[str, str]] = [{
        "role": "system",
        "content": CHAT_SYSTEM_PROMPT.format(
            digest=digest,
            retrieval_context=retrieval_context or "未检索到与问题直接相关的逐字稿片段。",
        ),
    }]
    for m in history:
        role = m.get("role")
        if role in {"user", "assistant"} and m.get("content"):
            messages.append({"role": role, "content": m["content"]})
    messages.append({"role": "user", "content": message})

    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": 0.4, "num_ctx": 8192},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_ENDPOINT}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _opener().open(request, timeout=600) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message") or {}
                delta = msg.get("content")
                if delta:
                    yield delta
                if obj.get("done"):
                    return
    except urllib.error.URLError as exc:
        raise RuntimeError("无法连接本地 Ollama。请确认服务已启动。") from exc
