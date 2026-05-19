from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional

from .memory_monitor import MemoryBudget
from .model_router import TaskKind, route
from .ollama_lifecycle import OllamaClient, unload_model
from .transcript_chunker import Chunk


L1_PROMPT_TEMPLATE = """/no_think
你是访谈研究助理。下面是 1对1 访谈的第 {chunk_index}/{chunk_total} 段逐字稿。

请严格按 JSON 结构输出，不要解释，不要 Markdown 代码块：

{{
  "topics": ["本段涉及的 1-3 个话题（短句，不超过 20 字）"],
  "quotes": [
    {{"speaker": "原文出现的说话人标签", "text": "重要原话（不超过 60 字）", "time": "MM:SS-MM:SS"}}
  ],
  "entities": ["人名/机构/时间/地点/术语，去重"],
  "questions_raised": ["访谈中明显悬而未决的问题（如有）"]
}}

要求：
- 只用逐字稿里出现过的内容，不编造
- quotes 最多 3 条，挑最有研究价值的
- entities 限 10 个以内
- 若某字段无内容，用空数组 []

逐字稿：
{chunk_text}
"""


@dataclass
class L1Result:
    chunk_index: int
    topics: List[str] = field(default_factory=list)
    quotes: List[dict] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    questions_raised: List[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict:
        return {
            "chunk_index": self.chunk_index,
            "topics": self.topics,
            "quotes": self.quotes,
            "entities": self.entities,
            "questions_raised": self.questions_raised,
        }


def extract_l1(chunk: Chunk, total_chunks: int,
               budget: Optional[MemoryBudget] = None,
               user_pref: str = "auto",
               client: Optional[OllamaClient] = None,
               keep_alive: str = "5m") -> L1Result:
    budget = budget or MemoryBudget.detect()
    choice = route(TaskKind.L1_EXTRACT, budget, user_pref=user_pref)
    client = client or OllamaClient()

    prompt = L1_PROMPT_TEMPLATE.format(
        chunk_index=chunk.index + 1,
        chunk_total=total_chunks,
        chunk_text=chunk.text,
    )
    raw = client.generate(
        model=choice.model,
        prompt=prompt,
        num_ctx=choice.num_ctx,
        temperature=0.2,
        keep_alive=keep_alive,
    )
    return _parse_l1(raw, chunk.index)


def _scan_json_object(raw: str, search_from: int = 0) -> Optional[tuple]:
    """扫描从 search_from 起的首个完整顶层 JSON 对象。返回 (block_text, end_index)，尊重字符串内的转义。"""
    start = raw.find("{", search_from)
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return raw[start:i + 1], i + 1
    return None


def _extract_first_json_object(raw: str) -> Optional[str]:
    """从可能含前后噪声的文本中提取首个完整的顶层 JSON 对象，尊重字符串内的转义。"""
    result = _scan_json_object(raw, 0)
    if result is None:
        return None
    return result[0]


def _parse_l1(raw: str, chunk_index: int) -> L1Result:
    # 扫描所有顶层 JSON 对象，挑首个可解析的；防御 <think>{...}</think> 噪声
    cursor = 0
    data = None
    while True:
        scan = _scan_json_object(raw, cursor)
        if scan is None:
            break
        block, end = scan
        try:
            data = json.loads(block)
            break
        except json.JSONDecodeError:
            cursor = end
            continue

    if data is None:
        return L1Result(chunk_index=chunk_index, raw_text=raw)

    return L1Result(
        chunk_index=chunk_index,
        topics=list(data.get("topics", []) or [])[:5],
        quotes=list(data.get("quotes", []) or [])[:5],
        entities=list(data.get("entities", []) or [])[:10],
        questions_raised=list(data.get("questions_raised", []) or [])[:5],
        raw_text=raw,
    )


L2_PROMPT_TEMPLATE = """/no_think
你是严谨的访谈研究助理。下面是一份 1对1 访谈所有分段的结构化要点（按时间顺序）。
请综合成一份完整的访谈总结，输出中文 Markdown。

要求：
- 输出 4 个 `##` 段：「访谈概览」「主要主题脉络」「关键观点与引用」「待跟进问题」
- 「主要主题脉络」按时间顺序，列出 3-7 个主题，每个 1-2 句概括
- 「关键观点与引用」挑 5-10 条最有研究价值的原话，附说话人和时间
- 不引入要点之外的信息；不重复同一引用
- 区分受访者（受访者通常是回答者）和研究者（研究者通常是提问者）的观点
- 整体 800-1500 字
- 直接输出 Markdown，不要写思考过程

分段要点：
{digest}
"""


def format_l1_digest(results: List[L1Result]) -> str:
    lines: List[str] = []
    for r in results:
        lines.append(f"### 分段 {r.chunk_index + 1}")
        if r.topics:
            lines.append("话题：" + "；".join(r.topics))
        if r.quotes:
            lines.append("引用：")
            for q in r.quotes:
                spk = q.get("speaker", "?")
                text = q.get("text", "")
                t = q.get("time", "")
                lines.append(f"  - [{t}] {spk}：{text}")
        if r.entities:
            lines.append("实体：" + "、".join(r.entities))
        if r.questions_raised:
            lines.append("悬而未决：" + "；".join(r.questions_raised))
        lines.append("")
    return "\n".join(lines)


def synthesize_l2(results: List[L1Result],
                  budget: Optional[MemoryBudget] = None,
                  user_pref: str = "auto",
                  client: Optional[OllamaClient] = None,
                  unload_after: bool = False) -> str:
    """把 L1 列表综合成 Markdown 总结。"""
    budget = budget or MemoryBudget.detect()
    choice = route(TaskKind.L2_SYNTHESIS, budget, user_pref=user_pref)
    client = client or OllamaClient()

    digest = format_l1_digest(results)
    prompt = L2_PROMPT_TEMPLATE.format(digest=digest)
    try:
        return client.generate(
            model=choice.model,
            prompt=prompt,
            num_ctx=choice.num_ctx,
            temperature=0.3,
            keep_alive="5m" if not unload_after else "0",
        )
    finally:
        if unload_after:
            unload_model(choice.model)
