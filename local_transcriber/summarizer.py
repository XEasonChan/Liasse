from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Iterable, List

from .models import SummaryResult, TranscriptSegment
from .timefmt import format_clock


class SummaryError(RuntimeError):
    pass


class OllamaSummarizer:
    def __init__(self, model: str = "qwen3:8b", endpoint: str = "http://127.0.0.1:11434") -> None:
        self.model = model
        self.endpoint = endpoint.rstrip("/")

    def summarize(self, segments: Iterable[TranscriptSegment]) -> SummaryResult:
        chunks = chunk_transcript(list(segments))
        if not chunks:
            return SummaryResult(model=self.model, text="没有可总结的转录文本。", chunks=[])

        chunk_summaries: List[str] = []
        for index, chunk in enumerate(chunks, start=1):
            prompt = build_chunk_prompt(chunk, index, len(chunks))
            chunk_summaries.append(self._generate(prompt))

        final_prompt = build_final_prompt(chunk_summaries)
        final_summary = self._generate(final_prompt)
        return SummaryResult(model=self.model, text=final_summary, chunks=chunk_summaries)

    def _generate(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_ctx": 8192,
                },
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.endpoint}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise SummaryError(
                "无法连接本地 Ollama。请确认 Ollama 已启动，并已下载摘要模型。"
            ) from exc
        return str(data.get("response", "")).strip()


def chunk_transcript(
    segments: List[TranscriptSegment],
    target_chars: int = 6500,
) -> List[str]:
    chunks: List[str] = []
    current: List[str] = []
    current_chars = 0

    for segment in segments:
        line = f"[{format_clock(segment.start)}-{format_clock(segment.end)}] {segment.speaker}: {segment.text}"
        if current and current_chars + len(line) > target_chars:
            chunks.append("\n".join(current))
            current = []
            current_chars = 0
        current.append(line)
        current_chars += len(line)

    if current:
        chunks.append("\n".join(current))
    return chunks


def build_chunk_prompt(chunk: str, index: int, total: int) -> str:
    return f"""你是严谨的学术访谈研究助理。请只根据下面这段逐字稿做分块摘要，不要编造没有出现的信息。

输出中文，包含：
1. 本段核心观点
2. 重要细节和例子
3. 可用于质性编码的主题标签
4. 值得回看原文的时间点

这是第 {index}/{total} 段逐字稿：

{chunk}
"""


def build_final_prompt(chunk_summaries: List[str]) -> str:
    joined = "\n\n---\n\n".join(chunk_summaries)
    return f"""你是严谨的学术访谈研究助理。请根据多个分块摘要，整合成一份访谈总摘要。

要求：
1. 不引入逐字稿之外的信息
2. 区分受访者观点、研究者追问、可能的解释
3. 输出“总览”“关键主题”“可引用片段线索”“后续分析建议”
4. 保持克制，不做过度推断

分块摘要如下：

{joined}
"""
