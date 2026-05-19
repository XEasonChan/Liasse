from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .hierarchical_summary import L1Result, extract_l1, synthesize_l2
from .memory_monitor import MemoryBudget, MemoryTier
from .model_router import TaskKind, route
from .models import TranscriptSegment
from .ollama_lifecycle import unload_model
from .transcript_chunker import chunk_interview
from .transcript_index import TranscriptIndex


@dataclass
class ProgressEvent:
    phase: str
    message: str
    value: float
    current: Optional[int] = None
    total: Optional[int] = None


ProgressCb = Callable[[ProgressEvent], None]


@dataclass
class AnalysisResult:
    summary_markdown: str
    l1_results: List[L1Result]
    index_path: Path
    chunks_count: int
    model_used_l1: str
    model_used_l2: str

    def to_dict(self) -> dict:
        return {
            "summary_markdown": self.summary_markdown,
            "l1_results": [r.to_dict() for r in self.l1_results],
            "index_path": str(self.index_path),
            "chunks_count": self.chunks_count,
            "model_used_l1": self.model_used_l1,
            "model_used_l2": self.model_used_l2,
        }


_STATE_DB_NAME = "analysis_state.db"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS l1_results (
    task_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunks_fingerprint TEXT NOT NULL,
    l1_json TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (task_id, chunk_index)
);
"""


def _fingerprint_chunks(chunks) -> str:
    import hashlib
    h = hashlib.sha1()
    for c in chunks:
        h.update(f"{c.index}|{c.start_time:.3f}|{c.end_time:.3f}|{len(c.text)}|".encode("utf-8"))
        h.update(c.text.encode("utf-8"))
    return h.hexdigest()


def _open_state_db(output_dir: Path) -> sqlite3.Connection:
    output_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(output_dir / _STATE_DB_NAME)
    con.executescript(_SCHEMA)
    return con


def load_existing_l1(output_dir: Path, task_id: str,
                     expected_fingerprint: Optional[str] = None) -> Dict[int, L1Result]:
    """加载已完成的 L1 结果。若 expected_fingerprint 给定，只返回 fingerprint 匹配的行。"""
    db_path = output_dir / _STATE_DB_NAME
    if not db_path.exists():
        return {}
    con = sqlite3.connect(db_path)
    try:
        if expected_fingerprint is not None:
            rows = con.execute(
                "SELECT chunk_index, l1_json FROM l1_results "
                "WHERE task_id = ? AND chunks_fingerprint = ? ORDER BY chunk_index",
                (task_id, expected_fingerprint),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT chunk_index, l1_json FROM l1_results "
                "WHERE task_id = ? ORDER BY chunk_index",
                (task_id,),
            ).fetchall()
    finally:
        con.close()
    out: Dict[int, L1Result] = {}
    for chunk_index, l1_json in rows:
        data = json.loads(l1_json)
        out[chunk_index] = L1Result(
            chunk_index=chunk_index,
            topics=list(data.get("topics", []) or []),
            quotes=list(data.get("quotes", []) or []),
            entities=list(data.get("entities", []) or []),
            questions_raised=list(data.get("questions_raised", []) or []),
            raw_text=data.get("raw_text", ""),
        )
    return out


def save_l1_result(output_dir: Path, task_id: str, l1: L1Result,
                   chunks_fingerprint: str = "") -> None:
    con = _open_state_db(output_dir)
    try:
        con.execute(
            "INSERT OR REPLACE INTO l1_results "
            "(task_id, chunk_index, chunks_fingerprint, l1_json, completed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (task_id, l1.chunk_index, chunks_fingerprint,
             json.dumps(l1.to_dict(), ensure_ascii=False),
             datetime.now(timezone.utc).isoformat()),
        )
        con.commit()
    finally:
        con.close()


def analyze(
    segments: List[TranscriptSegment],
    output_dir: Path,
    task_id: str,
    budget: Optional[MemoryBudget] = None,
    user_pref: str = "auto",
    on_progress: Optional[ProgressCb] = None,
) -> AnalysisResult:
    budget = budget or MemoryBudget.detect()
    emit = on_progress or (lambda _ev: None)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    chunks = chunk_interview(segments)
    if not chunks:
        raise ValueError("没有可分析的片段")
    n = len(chunks)
    emit(ProgressEvent("chunking", f"切分为 {n} 块", 0.05, current=n, total=n))

    l1_choice = route(TaskKind.L1_EXTRACT, budget, user_pref=user_pref)
    l2_choice = route(TaskKind.L2_SYNTHESIS, budget, user_pref=user_pref)

    fingerprint = _fingerprint_chunks(chunks)
    existing = load_existing_l1(output_dir, task_id, expected_fingerprint=fingerprint)
    l1_map: Dict[int, L1Result] = dict(existing)

    if existing:
        emit(ProgressEvent(
            "resume",
            f"恢复已完成的 L1 {len(existing)}/{n} 块",
            0.05 + 0.60 * (len(existing) / n),
            current=len(existing), total=n,
        ))

    for i, chunk in enumerate(chunks):
        if chunk.index in l1_map:
            continue
        emit(ProgressEvent(
            "l1",
            f"L1 抽取 {i + 1}/{n}（{l1_choice.model}）",
            0.05 + 0.60 * (i + 1) / n,
            current=i + 1, total=n,
        ))
        l1 = extract_l1(chunk, total_chunks=n,
                        budget=budget, user_pref=user_pref,
                        keep_alive="5m")
        l1_map[chunk.index] = l1
        save_l1_result(output_dir, task_id, l1, chunks_fingerprint=fingerprint)

    # 若所有 L1 都从缓存取回（resume），仍需发一个 l1 phase 事件以保证 UI 看到该阶段
    if not any(c.index not in existing for c in chunks):
        emit(ProgressEvent(
            "l1",
            f"L1 阶段已全部从缓存恢复 ({n}/{n})",
            0.05 + 0.60,
            current=n, total=n,
        ))

    # 按 chunk_index 排序，转回 list
    l1_results = [l1_map[c.index] for c in chunks]

    if l1_choice.model != l2_choice.model:
        emit(ProgressEvent(
            "model_switch",
            f"卸载 {l1_choice.model}，切换到 {l2_choice.model}",
            0.67,
        ))
        unload_model(l1_choice.model)

    emit(ProgressEvent("l2", f"L2 综合（{l2_choice.model}）", 0.70))
    summary_md = synthesize_l2(l1_results, budget=budget, user_pref=user_pref)

    # tight 内存：L2 完成后卸载，让出 RAM 给 QA
    if budget.tier == MemoryTier.TIGHT:
        emit(ProgressEvent("cleanup", f"卸载 {l2_choice.model} 释放内存", 0.82))
        unload_model(l2_choice.model)

    emit(ProgressEvent("indexing", "建立检索索引", 0.88))
    index_db = output_dir / "transcript_index.db"
    idx = TranscriptIndex.build(chunks, db_path=index_db)
    idx.save()

    (output_dir / "l1_results.json").write_text(
        json.dumps([r.to_dict() for r in l1_results],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    emit(ProgressEvent("done", "完成", 1.0))
    return AnalysisResult(
        summary_markdown=summary_md,
        l1_results=l1_results,
        index_path=index_db,
        chunks_count=n,
        model_used_l1=l1_choice.model,
        model_used_l2=l2_choice.model,
    )
