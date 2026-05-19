from local_transcriber.transcript_chunker import Chunk
from local_transcriber.transcript_index import TranscriptIndex


def _chunk(idx, text, start=0.0, end=60.0):
    return Chunk(
        index=idx, text=text, segment_ids=[idx],
        start_time=start, end_time=end, speaker_set={"A", "B"},
    )


def test_index_returns_chunks_matching_query():
    chunks = [
        _chunk(0, "A: 关于教育公平的看法\nB: 我觉得资源分配是核心"),
        _chunk(1, "A: 那经济呢\nB: 经济和教育密不可分"),
        _chunk(2, "A: 完全无关的话题\nB: 比如天气"),
    ]
    idx = TranscriptIndex.build(chunks)
    results = idx.search("教育公平", top_k=2)
    assert len(results) >= 1
    assert results[0].chunk.index == 0


def test_index_bm25_ranks_by_relevance():
    chunks = [
        _chunk(0, "教育 教育 教育 教育"),
        _chunk(1, "教育 一次"),
        _chunk(2, "其他话题"),
    ]
    idx = TranscriptIndex.build(chunks)
    results = idx.search("教育", top_k=3)
    assert results[0].chunk.index == 0
    assert results[0].score > results[1].score


def test_index_handles_chinese_segmentation():
    chunks = [
        _chunk(0, "B: 我对人工智能的态度是谨慎乐观"),
        _chunk(1, "B: 我们讨论了能源转型"),
    ]
    idx = TranscriptIndex.build(chunks)
    results = idx.search("人工智能", top_k=2)
    assert results[0].chunk.index == 0


def test_index_empty_query_returns_empty():
    chunks = [_chunk(0, "内容")]
    idx = TranscriptIndex.build(chunks)
    assert idx.search("", top_k=5) == []


def test_index_persists_to_sqlite(tmp_path):
    chunks = [_chunk(0, "A: 话题一"), _chunk(1, "B: 话题二")]
    db = tmp_path / "idx.db"
    idx = TranscriptIndex.build(chunks, db_path=db)
    idx.save()

    reopened = TranscriptIndex.load(db_path=db)
    results = reopened.search("话题二", top_k=1)
    assert results[0].chunk.index == 1
