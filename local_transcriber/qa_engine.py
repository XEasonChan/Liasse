from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional

from .memory_monitor import MemoryBudget
from .model_router import TaskKind, route
from .ollama_lifecycle import OllamaClient
from .timefmt import format_clock
from .transcript_index import SearchResult, TranscriptIndex


QA_SYSTEM_PROMPT = """你是访谈研究助理。下面是用户访谈的相关片段（按 BM25 关键词匹配排序，可能漏掉同义表达）：

{context}

回答规则：
- 只用上面片段里的内容；如果片段未提及，明确说"片段中未提及"
- 引用观点时附带说话人和时间窗口（如 [05:30-05:45] B）
- 如果用户的问题在片段里以不同措辞出现，先指出再回答
- 用中文，简洁，不展示思考过程
- 区分受访者 B 的观点和研究者 A 的追问
"""


_NO_MATCH_NOTE = "（注意：未检索到与问题强相关的片段，请如实告知用户无法回答。）"


@dataclass
class QAEngine:
    index: TranscriptIndex
    budget: MemoryBudget
    user_pref: str = "auto"

    def answer(self, question: str, history: List[dict],
               top_k: Optional[int] = None,
               client: Optional[OllamaClient] = None) -> Iterator[str]:
        if self.index is None:
            raise ValueError("QAEngine.index 不能为 None；先用 TranscriptIndex.build 建立索引")
        choice = route(TaskKind.QA, self.budget, user_pref=self.user_pref)
        client = client or OllamaClient()

        effective_top_k = top_k if top_k is not None else (3 if choice.num_ctx <= 8192 else 5)
        results = self.index.search(question, top_k=effective_top_k)
        context_str = self._format_context(results)
        system_content = QA_SYSTEM_PROMPT.format(context=context_str)

        messages: List[dict] = [{"role": "system", "content": system_content}]
        for m in history:
            if m.get("role") in {"user", "assistant"} and m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": question})

        yield from client.stream_chat(
            model=choice.model,
            messages=messages,
            num_ctx=choice.num_ctx,
            temperature=0.4,
            keep_alive="5m",
        )

    @staticmethod
    def _format_context(results: List[SearchResult]) -> str:
        if not results:
            return _NO_MATCH_NOTE
        parts: List[str] = []
        for r in results:
            parts.append(
                f"--- 片段 {r.chunk.index + 1} "
                f"[{format_clock(r.chunk.start_time)}-{format_clock(r.chunk.end_time)}], "
                f"score={r.score:.2f} ---\n{r.chunk.text}"
            )
        return "\n\n".join(parts)
