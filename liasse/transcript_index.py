from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

try:
    import jieba
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

from .transcript_chunker import Chunk


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[一-鿿]")


def _tokenize(text: str) -> List[str]:
    if _HAS_JIEBA:
        return [t for t in jieba.lcut(text) if t.strip() and not t.isspace()]
    # fallback：粗粒度 char-level 中文 + 英文 token
    return _TOKEN_RE.findall(text)


@dataclass
class SearchResult:
    chunk: Chunk
    score: float


@dataclass
class TranscriptIndex:
    chunks: List[Chunk]
    db_path: Optional[Path] = None
    _df: Dict[str, int] = field(default_factory=dict)
    _tf: List[Counter] = field(default_factory=list)
    _avgdl: float = 0.0

    K1: float = 1.5
    B: float = 0.75

    @classmethod
    def build(cls, chunks: List[Chunk], db_path: Optional[Path] = None) -> "TranscriptIndex":
        idx = cls(chunks=chunks, db_path=db_path)
        idx._index()
        return idx

    def _index(self) -> None:
        self._df = defaultdict(int)
        self._tf = []
        total_len = 0
        for c in self.chunks:
            tokens = _tokenize(c.text)
            tf = Counter(tokens)
            self._tf.append(tf)
            for term in tf:
                self._df[term] += 1
            total_len += len(tokens)
        self._avgdl = total_len / max(len(self.chunks), 1)

    def search(self, query: str, top_k: int = 5) -> List[SearchResult]:
        if not query.strip():
            return []
        terms = _tokenize(query)
        N = len(self.chunks)
        scored: List[SearchResult] = []
        for i, tf in enumerate(self._tf):
            dl = sum(tf.values()) or 1
            score = 0.0
            for term in terms:
                df = self._df.get(term, 0)
                if df == 0:
                    continue
                idf = math.log(1 + (N - df + 0.5) / (df + 0.5))
                freq = tf.get(term, 0)
                norm = freq * (self.K1 + 1) / (
                    freq + self.K1 * (1 - self.B + self.B * dl / (self._avgdl or 1))
                )
                score += idf * norm
            if score > 0:
                scored.append(SearchResult(chunk=self.chunks[i], score=score))
        scored.sort(key=lambda r: -r.score)
        return scored[:top_k]

    def save(self) -> None:
        if not self.db_path:
            raise ValueError("save() 需要 db_path")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db_path)
        con.executescript("""
            DROP TABLE IF EXISTS chunks;
            CREATE TABLE chunks (
                idx INTEGER PRIMARY KEY,
                text TEXT,
                start_time REAL,
                end_time REAL,
                speakers TEXT,
                segment_ids TEXT
            );
        """)
        rows = [
            (c.index, c.text, c.start_time, c.end_time,
             json.dumps(sorted(c.speaker_set)),
             json.dumps(c.segment_ids))
            for c in self.chunks
        ]
        con.executemany("INSERT INTO chunks VALUES (?,?,?,?,?,?)", rows)
        con.commit()
        con.close()

    @classmethod
    def load(cls, db_path: Path) -> "TranscriptIndex":
        con = sqlite3.connect(db_path)
        rows = con.execute(
            "SELECT idx, text, start_time, end_time, speakers, segment_ids "
            "FROM chunks ORDER BY idx"
        ).fetchall()
        con.close()
        chunks = [
            Chunk(
                index=r[0], text=r[1], start_time=r[2], end_time=r[3],
                speaker_set=set(json.loads(r[4])),
                segment_ids=json.loads(r[5]),
            )
            for r in rows
        ]
        return cls.build(chunks, db_path=db_path)
